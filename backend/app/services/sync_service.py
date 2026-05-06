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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlmodel import Session

from ..core.logging import get_logger
from ..db.models import Account, DataSource
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

_logger = get_logger(__name__)


@dataclass(slots=True)
class SyncOutcome:
    account_id: int
    success: bool
    message: str
    balance_count: int = 0
    position_count: int = 0
    synced_at: datetime = field(default_factory=_utcnow)


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

    try:
        balances = client.fetch_balance()
        positions = client.fetch_positions()
    except Exception as exc:
        return _record_failure(session, account, f"fetch failed: {exc}", started)
    finally:
        client.close()

    mapper = SymbolMapper(session)
    normalised_balances = normalize_balances(
        account_id=account.id or 0, raws=balances, source=DataSource.API
    )
    normalised_positions = normalize_positions(
        account_id=account.id or 0,
        exchange_name=_exchange_name(session, account),
        raws=positions,
        mapper=mapper,
        source=DataSource.API,
    )

    try:
        upsert_balances(session, account.id or 0, normalised_balances)
        upsert_positions(session, account.id or 0, normalised_positions)
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
        position_count=len(normalised_positions),
        synced_at=started,
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


def sync_all_accounts() -> list[SyncOutcome]:
    """Run sync for every enabled account; isolating failures per account."""

    results: list[SyncOutcome] = []
    with session_scope() as session:
        accounts = list_active_accounts(session)

    for acc in accounts:
        try:
            with session_scope() as session:
                refreshed: Optional[Account] = session.get(Account, acc.id)
                if refreshed is None or not refreshed.enabled:
                    continue
                results.append(sync_account(session, refreshed))
        except Exception as exc:  # pragma: no cover - belt and braces
            _logger.exception("unexpected sync failure account=%s", acc.id)
            results.append(
                SyncOutcome(
                    account_id=acc.id or 0,
                    success=False,
                    message=f"unexpected error: {exc}",
                    synced_at=_utcnow(),
                )
            )
    return results
