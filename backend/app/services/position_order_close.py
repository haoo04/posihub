"""FIFO close matching for order-level positions.

See ``docs/order-level-position.md`` (Phase 2) for the full specification.
A close action consumes ``PositionOrder`` rows in ``created_at`` ascending
order, recording each consumption as a ``PositionOrderMatch`` row tied to
a single ``PositionCloseExecution`` and decrementing the parent
``PositionCurrent.qty`` accordingly.

The whole operation runs inside a single transaction: any failure rolls
back so the position state never ends up partially updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from ..db.models import (
    DataSource,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionOrderMatch,
    PositionOrderStatus,
    PositionSide,
)

QTY_EPSILON = 1e-9


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FifoCloseError(ValueError):
    """Raised when a close request cannot be satisfied."""


@dataclass
class FifoCloseResult:
    execution: PositionCloseExecution
    matches: list[PositionOrderMatch]
    affected_orders: list[PositionOrder]
    realized_pnl: float


def _realized_pnl(
    side: PositionSide, open_price: float, close_price: float, qty: float
) -> float:
    if side == PositionSide.LONG:
        return (close_price - open_price) * qty
    if side == PositionSide.SHORT:
        return (open_price - close_price) * qty
    # NET (one-way) positions are treated as LONG for PnL sign convention,
    # mirroring how the unrealized PnL helper falls back today.
    return 0.0


def fifo_close_position(
    session: Session,
    *,
    position_id: int,
    close_qty: float,
    close_price: float,
    source: DataSource = DataSource.MANUAL,
    source_order_id: Optional[str] = None,
) -> FifoCloseResult:
    """Apply a FIFO close to ``position_id``.

    Args:
        session: Active SQLModel session. The caller controls commit;
            this function flushes but does not commit, so the API layer
            (or tests) can wrap the call in their own transaction.
        position_id: Parent ``PositionCurrent`` row.
        close_qty: Quantity to close. Must be > 0 and not exceed the
            sum of ``remaining_qty`` across the position's open orders.
        close_price: Execution price for this close action.
        source: Provenance tag for the close execution row.
        source_order_id: Optional exchange-side order id.

    Returns:
        A :class:`FifoCloseResult` summarising the new execution row,
        per-leg match rows, and orders whose ``remaining_qty`` / status
        changed.

    Raises:
        FifoCloseError: ``position_id`` is missing, ``close_qty`` is
            non-positive, or there is not enough open quantity to cover
            the request.
    """

    if close_qty <= 0:
        raise FifoCloseError("close_qty must be positive")

    position = session.get(PositionCurrent, position_id)
    if position is None:
        raise FifoCloseError(f"Position {position_id} not found")

    open_orders = list(
        session.exec(
            select(PositionOrder)
            .where(PositionOrder.position_id == position_id)
            .where(PositionOrder.remaining_qty > 0)
            .order_by(PositionOrder.created_at.asc(), PositionOrder.id.asc())
        ).all()
    )

    available = sum(o.remaining_qty for o in open_orders)
    if close_qty - available > QTY_EPSILON:
        raise FifoCloseError(
            f"close_qty {close_qty} exceeds available remaining qty {available}"
        )

    execution = PositionCloseExecution(
        position_id=position_id,
        close_qty=close_qty,
        close_price=close_price,
        source=source,
        source_order_id=source_order_id,
    )
    session.add(execution)
    session.flush()  # populate execution.id for the FK on matches

    matches: list[PositionOrderMatch] = []
    affected: list[PositionOrder] = []
    remaining_to_close = close_qty
    total_realized = 0.0
    now = _utcnow()

    for order in open_orders:
        if remaining_to_close <= QTY_EPSILON:
            break

        consume = min(order.remaining_qty, remaining_to_close)
        if consume <= 0:
            continue

        pnl = _realized_pnl(
            position.side, order.entry_price, close_price, consume
        )
        total_realized += pnl

        order.remaining_qty -= consume
        if order.remaining_qty <= QTY_EPSILON:
            order.remaining_qty = 0.0
            order.status = PositionOrderStatus.CLOSED
        else:
            order.status = PositionOrderStatus.PARTIAL
        order.updated_at = now
        session.add(order)
        affected.append(order)

        match = PositionOrderMatch(
            open_order_id=order.id,
            close_order_id=execution.id,
            matched_qty=consume,
            open_price=order.entry_price,
            close_price=close_price,
            realized_pnl=pnl,
            matched_at=now,
        )
        session.add(match)
        matches.append(match)

        remaining_to_close -= consume

    execution.realized_pnl = total_realized

    new_qty = position.qty - close_qty
    if abs(new_qty) <= QTY_EPSILON:
        new_qty = 0.0
    position.qty = new_qty
    position.updated_at = now
    session.add(position)

    session.flush()

    return FifoCloseResult(
        execution=execution,
        matches=matches,
        affected_orders=affected,
        realized_pnl=total_realized,
    )
