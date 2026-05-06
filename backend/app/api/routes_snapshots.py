"""Daily snapshot read endpoints + on-demand trigger."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from sqlmodel import select

from ..db.models import AccountSnapshotDaily, PositionSnapshotDaily
from ..schemas.snapshot import (
    AccountSnapshotRead,
    DailySnapshotResult,
    PositionSnapshotRead,
)
from ..services.snapshot_service import write_daily_snapshots
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/snapshots", tags=["snapshots"])


@router.get("/daily/accounts", response_model=list[AccountSnapshotRead])
def list_account_snapshots(
    session: SessionDep,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
) -> list[AccountSnapshotDaily]:
    stmt = select(AccountSnapshotDaily)
    if start is not None:
        stmt = stmt.where(AccountSnapshotDaily.snapshot_date >= start)
    if end is not None:
        stmt = stmt.where(AccountSnapshotDaily.snapshot_date <= end)
    if account_id is not None:
        stmt = stmt.where(AccountSnapshotDaily.account_id == account_id)
    stmt = stmt.order_by(AccountSnapshotDaily.snapshot_date.desc())  # type: ignore[attr-defined]
    return list(session.exec(stmt).all())


@router.get("/daily/positions", response_model=list[PositionSnapshotRead])
def list_position_snapshots(
    session: SessionDep,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    canonical_symbol: str | None = Query(default=None),
) -> list[PositionSnapshotDaily]:
    stmt = select(PositionSnapshotDaily)
    if start is not None:
        stmt = stmt.where(PositionSnapshotDaily.snapshot_date >= start)
    if end is not None:
        stmt = stmt.where(PositionSnapshotDaily.snapshot_date <= end)
    if account_id is not None:
        stmt = stmt.where(PositionSnapshotDaily.account_id == account_id)
    if canonical_symbol is not None:
        stmt = stmt.where(PositionSnapshotDaily.canonical_symbol == canonical_symbol)
    stmt = stmt.order_by(PositionSnapshotDaily.snapshot_date.desc())  # type: ignore[attr-defined]
    return list(session.exec(stmt).all())


@router.post("/daily/run", response_model=DailySnapshotResult)
def run_daily_snapshot() -> DailySnapshotResult:
    outcome = write_daily_snapshots()
    return DailySnapshotResult(
        snapshot_date=outcome.snapshot_date,
        accounts_written=outcome.accounts_written,
        positions_written=outcome.positions_written,
        balances_aggregated=outcome.balances_aggregated,
    )
