"""PnL time-series endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from ..db.models import AccountSnapshotDaily
from ..schemas.snapshot import PnlPoint, PnlSeries
from ..services.aggregate.pnl_calculator import aggregate_daily_equity, parse_range
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/pnl", tags=["pnl"])


@router.get("", response_model=PnlSeries)
def get_pnl_series(
    session: SessionDep,
    range: str = Query("30d", description="Time window: 7d / 30d / 90d / Nd"),
    asset: str = Query("USDT"),
) -> PnlSeries:
    try:
        days = parse_range(range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    stmt = select(
        AccountSnapshotDaily.snapshot_date,
        AccountSnapshotDaily.total_equity,
        AccountSnapshotDaily.total_unrealized_pnl,
    ).where(
        AccountSnapshotDaily.snapshot_date >= start_date,
        AccountSnapshotDaily.snapshot_date <= end_date,
        AccountSnapshotDaily.asset == asset.upper(),
    )

    rows = [(r[0], float(r[1] or 0.0), float(r[2] or 0.0)) for r in session.exec(stmt).all()]
    aggregated = aggregate_daily_equity(rows)
    return PnlSeries(
        range=range,
        asset=asset.upper(),
        points=[
            PnlPoint(
                snapshot_date=p.snapshot_date,
                total_equity=p.total_equity,
                total_unrealized_pnl=p.total_unrealized_pnl,
            )
            for p in aggregated
        ],
    )
