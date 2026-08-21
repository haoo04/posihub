"""Live exposure metrics for performance scope."""

from __future__ import annotations

from sqlmodel import Session, select

from ...db.models import Account, PositionCurrent
from ..pnl_calculator import position_unrealized_pnl_usdt
from .scope import PerformanceScope


def compute_live_exposure(
    session: Session, scope: PerformanceScope
) -> tuple[float, int]:
    """Return (total unrealized pnl USDT, open position count) for scope."""

    if not scope.account_ids:
        return 0.0, 0

    accounts = {
        int(a.id): a
        for a in session.exec(
            select(Account).where(Account.id.in_(scope.account_ids))
        ).all()
        if a.id is not None
    }

    positions = session.exec(
        select(PositionCurrent).where(
            PositionCurrent.account_id.in_(scope.account_ids)
        )
    ).all()

    total_upnl = 0.0
    open_count = 0
    for pos in positions:
        qty = float(pos.qty or 0.0)
        if qty <= 0:
            continue
        open_count += 1
        account = accounts.get(int(pos.account_id))
        total_upnl += position_unrealized_pnl_usdt(
            account_type=account.account_type if account else None,
            side=pos.side,
            unrealized_pnl=float(pos.unrealized_pnl or 0.0),
            mark_price=float(pos.mark_price or 0.0),
        )

    return total_upnl, open_count
