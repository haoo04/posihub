"""Dashboard overview endpoint."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from ..db.models import (
    Account,
    AccountBalanceCurrent,
    AccountSnapshotDaily,
    PositionCurrent,
)
from ..schemas.overview import OverviewResponse
from ..services.pnl_calculator import position_unrealized_pnl_usdt
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
def get_overview(session: SessionDep) -> OverviewResponse:
    accounts = list(session.exec(select(Account)).all())
    balances = list(session.exec(select(AccountBalanceCurrent)).all())
    positions = list(session.exec(select(PositionCurrent)).all())

    # Equity totals are summed per asset; we expose the USDT/USD bucket.
    equity_by_asset: dict[str, float] = defaultdict(float)
    for b in balances:
        equity_by_asset[b.asset.upper()] += float(b.equity or 0.0)

    total_equity = (
        equity_by_asset.get("USDT", 0.0)
        + equity_by_asset.get("USDC", 0.0)
        + equity_by_asset.get("USD", 0.0)
    )

    total_upnl = 0.0
    active_positions = 0
    account_by_id = {int(a.id): a for a in accounts if a.id is not None}
    for p in positions:
        if float(p.qty or 0.0) <= 0:
            continue
        active_positions += 1
        account = account_by_id.get(int(p.account_id))
        total_upnl += position_unrealized_pnl_usdt(
            account_type=account.account_type if account else None,
            side=p.side,
            unrealized_pnl=float(p.unrealized_pnl or 0.0),
            mark_price=float(p.mark_price or 0.0),
        )
    last_sync_at: Optional[datetime] = max(
        (a.last_sync_at for a in accounts if a.last_sync_at is not None), default=None
    )

    last_snapshot_at_dt = session.exec(
        select(func.max(AccountSnapshotDaily.created_at))
    ).one_or_none()

    return OverviewResponse(
        total_equity=total_equity,
        total_unrealized_pnl=total_upnl,
        total_positions=active_positions,
        total_accounts=len(accounts),
        last_snapshot_at=last_snapshot_at_dt,
        last_sync_at=last_sync_at,
    )
