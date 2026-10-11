"""FIFO and user-specified close matching for order-level positions.

See ``docs/order-level-position.md`` (Phase 2) for the full specification.
A close action consumes ``PositionOrder`` rows, recording each slice as a
``PositionOrderMatch`` tied to a single ``PositionCloseExecution`` and
refreshing the parent ``PositionCurrent`` (``qty``, ``entry_price``,
``unrealized_pnl``) from remaining order legs.

The whole operation runs inside a single transaction: any failure rolls
back so the position state never ends up partially updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, Optional

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
from .pnl_calculator import (
    get_quantity_context,
    linear_unrealized_pnl_usdt,
    quote_qty_tolerance,
    quote_to_entry_base,
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


def _apply_close_assignments(
    session: Session,
    *,
    position: PositionCurrent,
    execution: PositionCloseExecution,
    assignments: Iterable[tuple[PositionOrder, float]],
    now: datetime,
    inverse: bool = False,
) -> tuple[list[PositionOrderMatch], list[PositionOrder], float]:
    """Consume quantities on orders, write matches, set execution PnL.

    Does not flush; caller creates ``execution`` and flushes for id.
    """

    matches: list[PositionOrderMatch] = []
    affected: list[PositionOrder] = []
    total_realized = 0.0

    for order, consume in assignments:
        if consume <= (0 if inverse else QTY_EPSILON):
            continue

        pnl = _realized_pnl(
            position.side, order.entry_price, execution.close_price, consume
        )
        total_realized += pnl

        order.remaining_qty -= consume
        if order.remaining_qty <= (0 if inverse else QTY_EPSILON):
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
            close_price=execution.close_price,
            realized_pnl=pnl,
            matched_at=now,
        )
        session.add(match)
        matches.append(match)

    execution.realized_pnl = total_realized
    return matches, affected, total_realized


def _refresh_position_fields_from_orders(
    session: Session,
    position: PositionCurrent,
    *,
    now: datetime,
) -> None:
    """Sync ``qty``, ``entry_price``, and ``unrealized_pnl`` from order legs.

    If this position has no ``PositionOrder`` rows (exchange-only row), fields
    are left unchanged. Otherwise remaining quantities are authoritative for
    ``qty``; unrealized PnL matches the same convention as
    ``routes_position_orders.calculate_order_pnl`` summed over open quantity
    on each leg.
    """

    orders = list(
        session.exec(
            select(PositionOrder).where(PositionOrder.position_id == position.id)
        ).all()
    )
    if not orders:
        return

    inverse = (
        get_quantity_context(session, position.account_id, position.canonical_symbol)[
            "quantity_mode"
        ]
        == "quote_contract"
    )
    total_rem = sum(float(o.remaining_qty or 0.0) for o in orders)
    if total_rem <= (0 if inverse else QTY_EPSILON):
        position.qty = 0.0
        position.entry_price = 0.0
        position.unrealized_pnl = 0.0
        position.updated_at = now
        return

    mark = float(position.mark_price or 0.0)
    side = position.side

    upnl = 0.0
    cost = 0.0
    for o in orders:
        rq = float(o.remaining_qty or 0.0)
        if rq <= (0 if inverse else QTY_EPSILON):
            continue
        ep = float(o.entry_price or 0.0)
        cost += rq * ep
        upnl += linear_unrealized_pnl_usdt(side, ep, mark, rq)

    position.qty = total_rem
    position.unrealized_pnl = upnl
    if side in (PositionSide.LONG, PositionSide.SHORT):
        # Inverse legs store Q/E, so this is the USD-weighted harmonic entry price.
        position.entry_price = cost / total_rem
    position.updated_at = now


def refresh_account_positions_from_orders(
    session: Session,
    account_id: int,
    *,
    now: datetime | None = None,
) -> None:
    """Reconcile parent positions with order-level legs after a sync."""

    ts = now or _utcnow()
    positions = list(
        session.exec(
            select(PositionCurrent).where(PositionCurrent.account_id == account_id)
        ).all()
    )
    for position in positions:
        if position.id is None:
            continue
        has_orders = (
            session.exec(
                select(PositionOrder.id)
                .where(PositionOrder.position_id == position.id)
                .limit(1)
            ).first()
            is not None
        )
        if has_orders:
            _refresh_position_fields_from_orders(session, position, now=ts)
            session.add(position)


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

    if not isfinite(close_qty) or close_qty <= 0:
        raise FifoCloseError("close_qty must be positive")
    if not isfinite(close_price) or close_price <= 0:
        raise FifoCloseError("close_price must be positive")

    position = session.get(PositionCurrent, position_id)
    if position is None:
        raise FifoCloseError(f"Position {position_id} not found")
    try:
        inverse = (
            get_quantity_context(
                session,
                position.account_id,
                position.canonical_symbol,
                validate=True,
            )["quantity_mode"]
            == "quote_contract"
        )
    except ValueError as exc:
        raise FifoCloseError(str(exc)) from exc

    open_orders = list(
        session.exec(
            select(PositionOrder)
            .where(PositionOrder.position_id == position_id)
            .where(PositionOrder.remaining_qty > 0)
            .order_by(PositionOrder.created_at.asc(), PositionOrder.id.asc())
        ).all()
    )

    if inverse and any(o.entry_price <= 0 for o in open_orders):
        raise FifoCloseError("Bybit inverse close requires positive order entry_price")
    available = sum(
        o.remaining_qty * o.entry_price if inverse else o.remaining_qty for o in open_orders
    )
    tolerance = (
        sum(quote_qty_tolerance(o.entry_price) for o in open_orders) if inverse else QTY_EPSILON
    )
    if close_qty - available > tolerance:
        raise FifoCloseError(f"close_qty {close_qty} exceeds available remaining qty {available}")

    now = _utcnow()
    remaining_to_close = (
        available if inverse and abs(close_qty - available) <= tolerance else close_qty
    )
    assignments: list[tuple[PositionOrder, float]] = []

    for order in open_orders:
        if remaining_to_close <= (0 if inverse else QTY_EPSILON):
            break

        order_available = (
            order.remaining_qty * order.entry_price if inverse else order.remaining_qty
        )
        consume_external = min(order_available, remaining_to_close)
        if inverse and abs(remaining_to_close - order_available) <= quote_qty_tolerance(
            order.entry_price
        ):
            consume = order.remaining_qty
            consume_external = remaining_to_close
        elif inverse and consume_external == order_available:
            consume = order.remaining_qty
        else:
            consume = (
                quote_to_entry_base(consume_external, order.entry_price)
                if inverse
                else consume_external
            )
        if consume <= 0:
            continue

        assignments.append((order, consume))
        remaining_to_close -= consume_external

    execution = PositionCloseExecution(
        position_id=position_id,
        close_qty=sum(qty for _, qty in assignments) if inverse else close_qty,
        close_price=close_price,
        source=source,
        source_order_id=source_order_id,
    )
    session.add(execution)
    session.flush()

    matches, affected, total_realized = _apply_close_assignments(
        session,
        position=position,
        execution=execution,
        assignments=assignments,
        now=now,
        inverse=inverse,
    )

    _refresh_position_fields_from_orders(session, position, now=now)
    session.add(position)

    session.flush()

    return FifoCloseResult(
        execution=execution,
        matches=matches,
        affected_orders=affected,
        realized_pnl=total_realized,
    )


def specified_close_position(
    session: Session,
    *,
    position_id: int,
    close_qty: float,
    close_price: float,
    legs: list[tuple[int, float]],
    source: DataSource = DataSource.MANUAL,
    source_order_id: Optional[str] = None,
) -> FifoCloseResult:
    """Close ``close_qty`` by explicitly pairing open ``PositionOrder`` legs.

    ``legs`` is an ordered list of ``(open_order_id, qty)``. Each ``qty``
    must be positive, ``open_order_id`` values must be unique within the
    list, and the sum of quantities must equal ``close_qty`` within
    ``QTY_EPSILON``. Every referenced order must belong to ``position_id``
    and have sufficient ``remaining_qty``.

    Raises:
        FifoCloseError: Same family of validation errors as FIFO close.
    """

    if not isfinite(close_qty) or close_qty <= 0:
        raise FifoCloseError("close_qty must be positive")
    if not isfinite(close_price) or close_price <= 0:
        raise FifoCloseError("close_price must be positive")

    if not legs:
        raise FifoCloseError("legs must not be empty")

    position = session.get(PositionCurrent, position_id)
    if position is None:
        raise FifoCloseError(f"Position {position_id} not found")
    try:
        inverse = (
            get_quantity_context(
                session,
                position.account_id,
                position.canonical_symbol,
                validate=True,
            )["quantity_mode"]
            == "quote_contract"
        )
    except ValueError as exc:
        raise FifoCloseError(str(exc)) from exc

    seen_ids: set[int] = set()
    for open_order_id, qty in legs:
        if open_order_id in seen_ids:
            raise FifoCloseError(
                f"duplicate open_order_id {open_order_id} in legs"
            )
        seen_ids.add(open_order_id)
        if not isfinite(qty) or qty <= 0:
            raise FifoCloseError("each leg qty must be positive")

    open_orders = list(
        session.exec(
            select(PositionOrder)
            .where(PositionOrder.position_id == position_id)
            .where(PositionOrder.remaining_qty > 0)
        ).all()
    )

    by_id = {o.id: o for o in open_orders}
    assignments: list[tuple[PositionOrder, float]] = []
    leg_sum = 0.0

    for open_order_id, qty in legs:
        order = by_id.get(open_order_id)
        if order is None:
            raise FifoCloseError(
                f"open order {open_order_id} not found, not open, "
                f"or not on this position"
            )
        if inverse and order.entry_price <= 0:
            raise FifoCloseError("Bybit inverse close requires positive order entry_price")
        available = order.remaining_qty * order.entry_price if inverse else order.remaining_qty
        tolerance = quote_qty_tolerance(order.entry_price) if inverse else QTY_EPSILON
        if qty - available > tolerance:
            raise FifoCloseError(
                f"leg qty {qty} exceeds remaining_qty {available} "
                f"for order {open_order_id}"
            )
        consume = (
            order.remaining_qty
            if abs(qty - available) <= tolerance
            else quote_to_entry_base(qty, order.entry_price) if inverse else qty
        )
        assignments.append((order, consume))
        leg_sum += qty

    if abs(leg_sum - close_qty) > QTY_EPSILON:
        raise FifoCloseError(
            f"sum of leg quantities {leg_sum} must equal close_qty {close_qty}"
        )

    execution = PositionCloseExecution(
        position_id=position_id,
        close_qty=sum(qty for _, qty in assignments) if inverse else close_qty,
        close_price=close_price,
        source=source,
        source_order_id=source_order_id,
    )
    session.add(execution)
    session.flush()

    now = _utcnow()
    matches, affected, total_realized = _apply_close_assignments(
        session,
        position=position,
        execution=execution,
        assignments=assignments,
        now=now,
        inverse=inverse,
    )

    _refresh_position_fields_from_orders(session, position, now=now)
    session.add(position)

    session.flush()

    return FifoCloseResult(
        execution=execution,
        matches=matches,
        affected_orders=affected,
        realized_pnl=total_realized,
    )
