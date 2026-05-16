"""Aggregate realized PnL from close executions and order matches."""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

from ..db.models import PositionCloseExecution, PositionOrderMatch


def realized_pnl_totals_by_position_id(session: Session) -> dict[int, float]:
    """Sum ``PositionCloseExecution.realized_pnl`` per ``position_id``."""

    rows = session.exec(
        select(
            PositionCloseExecution.position_id,
            func.sum(PositionCloseExecution.realized_pnl),
        ).group_by(PositionCloseExecution.position_id)
    ).all()
    out: dict[int, float] = {}
    for row in rows:
        pid, total = row[0], row[1]
        if pid is not None:
            out[int(pid)] = float(total or 0.0)
    return out


def realized_pnl_totals_by_open_order_id(
    session: Session, order_ids: list[int]
) -> dict[int, float]:
    """Sum ``PositionOrderMatch.realized_pnl`` per ``open_order_id``."""

    if not order_ids:
        return {}
    rows = session.exec(
        select(
            PositionOrderMatch.open_order_id,
            func.sum(PositionOrderMatch.realized_pnl),
        )
        .where(PositionOrderMatch.open_order_id.in_(order_ids))
        .group_by(PositionOrderMatch.open_order_id)
    ).all()
    return {int(oid): float(total or 0.0) for oid, total in rows}
