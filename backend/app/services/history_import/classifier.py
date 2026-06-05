"""Load existing local order-level state for idempotent imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ...db.models import (
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionSide,
)


@dataclass(slots=True)
class LocalOpenOrder:
    id: int
    position_id: int
    source_order_id: Optional[str]
    canonical_symbol: str
    side: PositionSide
    entry_price: float
    remaining_qty: float
    created_at: datetime


@dataclass(slots=True)
class LocalCloseExecution:
    source_order_id: str
    close_qty: float
    close_price: float


@dataclass(slots=True)
class LocalState:
    """Snapshot of what already exists locally for an account.

    Used both to skip duplicates (``open_source_ids`` / ``close_source_ids``),
    to detect conflicts (the ``*_by_source_id`` maps), and to seed FIFO with
    open legs that still have remaining quantity (``seed_legs_by_group``).
    """

    open_source_ids: set[str] = field(default_factory=set)
    close_source_ids: set[str] = field(default_factory=set)
    open_by_source_id: dict[str, LocalOpenOrder] = field(default_factory=dict)
    close_by_source_id: dict[str, LocalCloseExecution] = field(default_factory=dict)
    seed_legs_by_group: dict[tuple[str, str], list[LocalOpenOrder]] = field(
        default_factory=dict
    )


def load_local_state(session: Session, account_id: int) -> LocalState:
    positions = list(
        session.exec(
            select(PositionCurrent).where(PositionCurrent.account_id == account_id)
        ).all()
    )
    pos_by_id = {p.id: p for p in positions if p.id is not None}
    if not pos_by_id:
        return LocalState()

    state = LocalState()

    orders = list(
        session.exec(
            select(PositionOrder).where(
                PositionOrder.position_id.in_(list(pos_by_id.keys()))  # type: ignore[union-attr]
            )
        ).all()
    )
    for order in orders:
        position = pos_by_id.get(order.position_id)
        if position is None or order.id is None:
            continue
        local = LocalOpenOrder(
            id=order.id,
            position_id=order.position_id,
            source_order_id=order.source_order_id,
            canonical_symbol=position.canonical_symbol,
            side=position.side,
            entry_price=float(order.entry_price or 0.0),
            remaining_qty=float(order.remaining_qty or 0.0),
            created_at=order.created_at,
        )
        if order.source_order_id:
            state.open_source_ids.add(order.source_order_id)
            state.open_by_source_id[order.source_order_id] = local
        if local.remaining_qty > 0:
            key = (position.canonical_symbol, position.side.value)
            state.seed_legs_by_group.setdefault(key, []).append(local)

    executions = list(
        session.exec(
            select(PositionCloseExecution).where(
                PositionCloseExecution.position_id.in_(list(pos_by_id.keys()))  # type: ignore[union-attr]
            )
        ).all()
    )
    for ex in executions:
        if ex.source_order_id:
            state.close_source_ids.add(ex.source_order_id)
            state.close_by_source_id[ex.source_order_id] = LocalCloseExecution(
                source_order_id=ex.source_order_id,
                close_qty=float(ex.close_qty or 0.0),
                close_price=float(ex.close_price or 0.0),
            )

    return state
