"""High level synchronisation orchestration.

Single entry point used by both the REST API and the scheduler.

Steps for a single account:

1. Build a CCXT connector via :func:`build_client_for_account`.
2. Fetch balances + positions.
3. Normalise (symbol mapping, asset upper-casing).
4. Persist into the *current* tables.
5. Update the account's sync metadata (success / failure).

A failure of one account never propagates to others.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlmodel import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..db.models import Account, AccountType, DataSource
from ..db.session import session_scope
from .exchange.factory import (
    build_client_for_account,
    get_account_or_404,
    list_active_accounts,
)
from .normalize.normalizer import (
    normalize_balances,
    normalize_positions,
    upsert_balances,
    upsert_positions,
)
from .normalize.symbol_mapper import SymbolMapper
from .position_market import instrument_hint_for_account
from .position_order_close import refresh_account_positions_from_orders
from .spot.position_deriver import derive_spot_positions

_logger = get_logger(__name__)


@dataclass(slots=True)
class SyncOutcome:
    account_id: int
    success: bool
    message: str
    balance_count: int = 0
    position_count: int = 0
    synced_at: datetime = field(default_factory=_utcnow)
    unmapped_symbols: list[str] = field(default_factory=list)


def _exchange_name(session: Session, account: Account) -> str:
    from ..db.models import Exchange

    exch = session.get(Exchange, account.exchange_id)
    return exch.name if exch else "unknown"


def sync_account(session: Session, account: Account) -> SyncOutcome:
    """Run a single-account sync inside the given session.

    Caller is responsible for committing/rolling back. Errors update
    metadata fields on the account row and are returned in the outcome.
    """

    if account.is_simulated:
        outcome = SyncOutcome(
            account_id=account.id or 0,
            success=True,
            message="simulated account skipped",
            synced_at=_utcnow(),
        )
        return outcome

    started = _utcnow()
    try:
        client = build_client_for_account(session, account)
    except Exception as exc:
        return _record_failure(session, account, f"build client failed: {exc}", started)

    exchange_name = _exchange_name(session, account)
    mapper = SymbolMapper(session)
    unmapped: list[str] = []

    try:
        balances = client.fetch_balance()
        if account.account_type == AccountType.SPOT:
            positions = derive_spot_positions(
                account_id=account.id or 0,
                exchange_name=exchange_name,
                balances=balances,
                client=client,
                mapper=mapper,
                source=DataSource.API,
                unmapped=unmapped,
            )
        elif account.account_type in (
            AccountType.USDT_PERP,
            AccountType.COIN_PERP,
            AccountType.FUTURES,
        ):
            positions = normalize_positions(
                account_id=account.id or 0,
                exchange_name=exchange_name,
                raws=client.fetch_positions(),
                mapper=mapper,
                source=DataSource.API,
                instrument_hint=instrument_hint_for_account(account.account_type),
                account_type=account.account_type,
                unmapped=unmapped,
            )
        elif account.account_type == AccountType.FUNDING:
            positions = []
        else:
            positions = []
    except Exception as exc:
        return _record_failure(session, account, f"fetch failed: {exc}", started)
    finally:
        client.close()

    normalised_balances = normalize_balances(
        account_id=account.id or 0, raws=balances, source=DataSource.API
    )
    normalised_positions = positions

    if unmapped:
        _logger.warning(
            "sync: unresolved symbols account=%s exchange=%s symbols=%s",
            account.id,
            exchange_name,
            unmapped,
        )

    try:
        upsert_balances(session, account.id or 0, normalised_balances)
        rows_written = upsert_positions(session, account.id or 0, normalised_positions)
        refresh_account_positions_from_orders(session, account.id or 0, now=started)
    except Exception as exc:
        return _record_failure(session, account, f"persist failed: {exc}", started)

    account.last_sync_at = started
    account.last_sync_status = "ok"
    account.last_sync_error = None
    account.consecutive_failures = 0
    session.add(account)

    return SyncOutcome(
        account_id=account.id or 0,
        success=True,
        message="ok",
        balance_count=len(normalised_balances),
        position_count=rows_written,
        synced_at=started,
        unmapped_symbols=list(unmapped),
    )


def _record_failure(
    session: Session, account: Account, message: str, started: datetime
) -> SyncOutcome:
    _logger.warning("sync failure account=%s err=%s", account.id, message)
    account.last_sync_at = started
    account.last_sync_status = "error"
    account.last_sync_error = message[:500]
    account.consecutive_failures = (account.consecutive_failures or 0) + 1
    session.add(account)
    return SyncOutcome(
        account_id=account.id or 0,
        success=False,
        message=message,
        synced_at=started,
    )


def sync_account_by_id(account_id: int) -> SyncOutcome:
    """Convenience wrapper used by the REST endpoint."""

    with session_scope() as session:
        account = get_account_or_404(session, account_id)
        return sync_account(session, account)


def _sync_one_committed(account_id: int) -> SyncOutcome:
    """Sync a single account inside its own session and commit at the end.

    Designed to be invoked from worker threads in :func:`sync_all_accounts`.
    The session is never shared across threads; only ``account_id`` (a plain
    int) crosses the thread boundary.
    """

    try:
        with session_scope() as session:
            account: Optional[Account] = session.get(Account, account_id)
            if account is None or not account.enabled:
                return SyncOutcome(
                    account_id=account_id,
                    success=False,
                    message="account missing or disabled",
                    synced_at=_utcnow(),
                )
            outcome = sync_account(session, account)
            return outcome
    except Exception as exc:  # pragma: no cover - belt and braces
        _logger.exception("unexpected sync failure account=%s", account_id)
        return SyncOutcome(
            account_id=account_id,
            success=False,
            message=f"unexpected error: {exc}",
            synced_at=_utcnow(),
        )


def sync_all_accounts(max_workers: Optional[int] = None) -> list[SyncOutcome]:
    """Run sync for every enabled account concurrently.

    Each account is processed in its own thread with an independent
    :class:`Session`; a failure of one account never propagates to others.
    Returns outcomes in completion order.
    """

    with session_scope() as session:
        account_ids = [
            acc.id for acc in list_active_accounts(session) if acc.id is not None
        ]

    if not account_ids:
        return []

    workers = max_workers if max_workers is not None else get_settings().sync_max_workers
    workers = max(1, min(workers, len(account_ids)))

    results: list[SyncOutcome] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="posihub-sync") as pool:
        futures = [pool.submit(_sync_one_committed, aid) for aid in account_ids]
        for fut in as_completed(futures):
            results.append(fut.result())
    return results
