"""History import (API backfill) endpoints: preview then commit."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..core.logging import get_logger
from ..db.models import (
    Account,
    AccountType,
    Exchange,
    HistoryImportPreview,
)
from ..schemas.history_import import (
    HistoryImportCommitRequest,
    HistoryImportCommitResponse,
    HistoryImportPreviewRequest,
    HistoryImportPreviewResponse,
)
from ..services.exchange.factory import build_client_for_account
from ..services.history_import.bitget_fetcher import fetch_bitget_history
from ..services.history_import.classifier import load_local_state
from ..services.history_import.committer import (
    HistoryImportError,
    commit_history_import,
)
from ..services.history_import.serialization import (
    order_from_dict,
    order_to_dict,
    closed_position_to_dict,
)
from ..services.history_import.scope import canonical_matches_bitget_product
from ..services.history_import.simulator import simulate
from ..services.normalize.symbol_mapper import SymbolMapper
from .deps import SessionDep

router = APIRouter(prefix="/api/v1", tags=["history-import"])

_logger = get_logger(__name__)

_PREVIEW_TTL = timedelta(minutes=30)
_SUPPORTED_ACCOUNT_TYPES = {AccountType.USDT_PERP, AccountType.COIN_PERP}


def _to_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _require_backfillable_account(session: SessionDep, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    if account.is_simulated:
        raise HTTPException(
            status_code=400, detail="simulated accounts have no exchange history"
        )
    if account.account_type not in _SUPPORTED_ACCOUNT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="history backfill supports usdt_perp / coin_perp accounts only",
        )
    exchange = session.get(Exchange, account.exchange_id)
    if exchange is None or exchange.name.lower() != "bitget":
        raise HTTPException(
            status_code=400, detail="history backfill currently supports Bitget only"
        )
    return account


def _pnl_validation_warnings(preview, closed_positions) -> int:
    """Count (canonical, side) groups whose simulated PnL drifts from Bitget."""

    reported: dict[tuple[str, str], float] = {}
    for cp in closed_positions:
        key = (cp.canonical_symbol or cp.raw_symbol, cp.side.value)
        reported[key] = reported.get(key, 0.0) + cp.realized_pnl

    simulated: dict[tuple[str, str], float] = {}
    for order in preview.orders:
        if not order.matches:
            continue
        key = (order.canonical_symbol or order.raw_symbol, order.side)
        for match in order.matches:
            simulated[key] = simulated.get(key, 0.0) + match.realized_pnl

    warnings = 0
    for key, value in reported.items():
        if abs(value - simulated.get(key, 0.0)) > 0.01:
            warnings += 1
    return warnings


@router.post(
    "/accounts/{account_id}/history-import/preview",
    response_model=HistoryImportPreviewResponse,
)
def preview_history_import(
    account_id: int,
    payload: HistoryImportPreviewRequest,
    session: SessionDep,
) -> HistoryImportPreviewResponse:
    account = _require_backfillable_account(session, account_id)
    if payload.until <= payload.since:
        raise HTTPException(status_code=400, detail="until must be after since")

    exchange = session.get(Exchange, account.exchange_id)
    exchange_name = exchange.name if exchange else "bitget"

    try:
        client = build_client_for_account(session, account)
    except Exception as exc:  # noqa: BLE001 - surface as 400 to the UI
        raise HTTPException(status_code=400, detail=f"build client failed: {exc}")

    mapper = SymbolMapper(session)
    try:
        fetch_result = fetch_bitget_history(
            client,
            mapper,
            exchange_name=exchange_name,
            since_ms=_to_ms(payload.since),
            until_ms=_to_ms(payload.until),
            account_type=account.account_type,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.exception("history fetch failed for account %s", account_id)
        raise HTTPException(status_code=502, detail=f"exchange fetch failed: {exc}")
    finally:
        client.close()

    if isinstance(fetch_result, tuple):  # compatibility with older test adapters
        orders, closed_positions = fetch_result
        fetch_stats = None
    else:
        orders = fetch_result.orders
        closed_positions = fetch_result.closed_positions
        fetch_stats = fetch_result.stats
    local_state = load_local_state(session, account_id)
    preview = simulate(orders, local_state, closed_positions=closed_positions)
    preview.summary.pnl_validation_warnings = _pnl_validation_warnings(
        preview, closed_positions
    )
    if fetch_stats is not None:
        preview.summary.unresolved_fill_time = fetch_stats.unresolved_fill_time
        preview.summary.filtered_out_of_scope = fetch_stats.filtered_out_of_scope
        preview.summary.fallback_time_orders = fetch_stats.fallback_time_orders

    preview_id = uuid.uuid4().hex
    now = _utcnow()
    payload_json = json.dumps(
        {
            "orders": [order_to_dict(o) for o in orders],
            "closed_positions": [closed_position_to_dict(c) for c in closed_positions],
        }
    )
    # Drop expired rows opportunistically to keep the cache table small.
    for stale in session.exec(
        select(HistoryImportPreview).where(HistoryImportPreview.expires_at < now)
    ).all():
        session.delete(stale)

    session.add(
        HistoryImportPreview(
            id=preview_id,
            account_id=account_id,
            payload_json=payload_json,
            created_at=now,
            expires_at=now + _PREVIEW_TTL,
        )
    )
    session.commit()

    return HistoryImportPreviewResponse(
        preview_id=preview_id,
        account_id=account_id,
        fetched_at=now,
        orders=preview.orders,
        closed_positions=preview.closed_positions,
        summary=preview.summary,
        blockers=preview.blockers,
    )


@router.post(
    "/accounts/{account_id}/history-import/commit",
    response_model=HistoryImportCommitResponse,
)
def commit_history_import_endpoint(
    account_id: int,
    payload: HistoryImportCommitRequest,
    session: SessionDep,
) -> HistoryImportCommitResponse:
    account = _require_backfillable_account(session, account_id)

    cached = session.get(HistoryImportPreview, payload.preview_id)
    if cached is None or cached.account_id != account_id:
        raise HTTPException(status_code=404, detail="preview not found")
    if cached.committed_at is not None:
        raise HTTPException(status_code=409, detail="preview already committed")
    if cached.expires_at < _utcnow():
        raise HTTPException(status_code=410, detail="preview expired, re-run preview")

    data = json.loads(cached.payload_json)
    orders = [order_from_dict(d) for d in data.get("orders", [])]

    # The preview is cached for up to 30 minutes.  Re-check the account scope
    # at commit time so an account-type edit or a stale/malicious cache cannot
    # write the other Bitget product into this ledger.
    for order in orders:
        if order.canonical_symbol and not canonical_matches_bitget_product(
            order.canonical_symbol, account.account_type
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"cached order {order.source_order_id} is outside "
                    f"the {account.account_type.value} product scope"
                ),
            )

    try:
        result = commit_history_import(session, account_id=account_id, orders=orders)
    except HistoryImportError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    cached.committed_at = _utcnow()
    session.add(cached)
    session.commit()

    return HistoryImportCommitResponse(
        account_id=account_id,
        created_opens=result.created_opens,
        created_closes=result.created_closes,
        skipped=result.skipped,
        conflicts=result.conflicts,
        orphans=result.orphans,
    )
