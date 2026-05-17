"""Manual entry endpoints for补录 / 模拟账户."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete

from ..db.models import (
    Account,
    DataSource,
    ManualEntry,
    ManualEntryType,
    PositionSnapshotDaily,
)
from ..schemas.snapshot import ManualSnapshotCreate, ManualSnapshotResult
from ..services.normalize.normalizer import (
    NormalizedBalance,
    NormalizedPosition,
    upsert_balances,
    upsert_positions,
)
from ..services.snapshot_service import write_account_snapshot
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/manual", tags=["manual"])


@router.post("/snapshot", response_model=ManualSnapshotResult)
def create_manual_snapshot(
    payload: ManualSnapshotCreate, session: SessionDep
) -> ManualSnapshotResult:
    account = session.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    source = DataSource.SIMULATED if account.is_simulated else DataSource.MANUAL

    total_equity = (
        payload.total_equity
        if payload.total_equity is not None
        else sum(b.equity for b in payload.balances)
    )

    write_account_snapshot(
        session,
        account_id=payload.account_id,
        snapshot_date=payload.snapshot_date,
        asset=payload.asset.upper(),
        total_equity=float(total_equity or 0.0),
        total_unrealized_pnl=payload.total_unrealized_pnl,
        total_available=payload.total_available,
        source=source,
    )

    # replace the daily position snapshots for the same account/date
    session.exec(  # type: ignore[call-arg]
        delete(PositionSnapshotDaily).where(
            PositionSnapshotDaily.snapshot_date == payload.snapshot_date,
            PositionSnapshotDaily.account_id == payload.account_id,
        )
    )

    for pos in payload.positions:
        session.add(
            PositionSnapshotDaily(
                snapshot_date=payload.snapshot_date,
                account_id=payload.account_id,
                canonical_symbol=pos.canonical_symbol,
                side=pos.side,
                qty=pos.qty,
                entry_price=pos.entry_price,
                mark_price=pos.mark_price,
                unrealized_pnl=pos.unrealized_pnl,
                source=source,
            )
        )

    # For simulated accounts, also reflect into "current" tables so the UI
    # immediately sees the new balances/positions without waiting for sync.
    if account.is_simulated:
        upsert_balances(
            session,
            payload.account_id,
            [
                NormalizedBalance(
                    account_id=payload.account_id,
                    asset=b.asset.upper(),
                    equity=b.equity,
                    available=b.available,
                    frozen=b.frozen,
                    source=source,
                )
                for b in payload.balances
            ],
        )
        upsert_positions(
            session,
            payload.account_id,
            [
                NormalizedPosition(
                    account_id=payload.account_id,
                    canonical_symbol=pos.canonical_symbol,
                    side=pos.side,
                    qty=pos.qty,
                    entry_price=pos.entry_price,
                    mark_price=pos.mark_price,
                    unrealized_pnl=pos.unrealized_pnl,
                    leverage=1.0,
                    margin_mode=None,
                    source=source,
                )
                for pos in payload.positions
            ],
        )

    # audit trail
    session.add(
        ManualEntry(
            entry_date=payload.snapshot_date,
            account_id=payload.account_id,
            entry_type=ManualEntryType.SNAPSHOT,
            payload_json=json.dumps(
                payload.model_dump(mode="json"),
                ensure_ascii=False,
            ),
            operator=payload.operator,
        )
    )

    session.commit()

    return ManualSnapshotResult(
        account_id=payload.account_id,
        snapshot_date=payload.snapshot_date,
        accounts_written=1,
        positions_written=len(payload.positions),
        balances_written=len(payload.balances) if account.is_simulated else 0,
    )
