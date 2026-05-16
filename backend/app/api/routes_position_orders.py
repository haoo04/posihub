"""Position Orders endpoints (order-level position tracking)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..core.config import get_settings
from ..db.models import PositionCurrent, PositionOrder, PositionOrderStatus, PositionSide
from ..services.realized_pnl_query import realized_pnl_totals_by_open_order_id
from ..schemas.position_order import (
    PositionOrderCreate,
    PositionOrderRead,
    PositionOrderUpdate,
    PositionOrderWithPnL,
)
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/position-orders", tags=["position-orders"])


def calculate_order_pnl(
    order: PositionOrder, mark_price: float, side: PositionSide
) -> tuple[float, float]:
    """Calculate unrealized PnL for an order.

    Args:
        order: Position order
        mark_price: Current mark price
        side: Position side (LONG/SHORT)

    Returns:
        Tuple of (unrealized_pnl, unrealized_pnl_pct)
    """
    qty = order.remaining_qty
    if qty == 0:
        return 0.0, 0.0

    if side == PositionSide.LONG:
        pnl = (mark_price - order.entry_price) * qty
    elif side == PositionSide.SHORT:
        pnl = (order.entry_price - mark_price) * qty
    else:  # NET
        pnl = 0.0

    # Calculate percentage based on entry value
    entry_value = order.entry_price * qty
    pnl_pct = (pnl / entry_value * 100) if entry_value != 0 else 0.0

    return pnl, pnl_pct


@router.get("", response_model=list[PositionOrderRead])
def list_position_orders(
    session: SessionDep,
    position_id: Optional[int] = None,
) -> list[PositionOrderRead]:
    """List all position orders, optionally filtered by position_id."""
    query = select(PositionOrder)
    if position_id is not None:
        query = query.where(PositionOrder.position_id == position_id)

    orders = list(session.exec(query).all())
    return [PositionOrderRead.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=PositionOrderWithPnL)
def get_position_order(session: SessionDep, order_id: int) -> PositionOrderWithPnL:
    """Get a single position order with calculated PnL."""
    order = session.get(PositionOrder, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position order {order_id} not found",
        )

    # Get the parent position to fetch mark_price and side
    position = session.get(PositionCurrent, order.position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent position {order.position_id} not found",
        )

    pnl, pnl_pct = calculate_order_pnl(order, position.mark_price, position.side)
    rp_map = realized_pnl_totals_by_open_order_id(session, [int(order.id or 0)])

    return PositionOrderWithPnL(
        **order.model_dump(),
        unrealized_pnl=pnl,
        unrealized_pnl_pct=pnl_pct,
        mark_price=position.mark_price,
        realized_pnl=float(rp_map.get(int(order.id or 0), 0.0)),
    )


@router.post("", response_model=PositionOrderRead, status_code=status.HTTP_201_CREATED)
def create_position_order(
    session: SessionDep, order_in: PositionOrderCreate
) -> PositionOrderRead:
    """Create a new position order."""
    # Validate that the position exists
    position = session.get(PositionCurrent, order_in.position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {order_in.position_id} not found",
        )

    # Create the order
    order = PositionOrder(
        **order_in.model_dump(),
        remaining_qty=order_in.open_qty,  # Initially remaining_qty = open_qty
        status=PositionOrderStatus.OPEN,
    )

    session.add(order)
    session.commit()
    session.refresh(order)

    return PositionOrderRead.model_validate(order)


@router.patch("/{order_id}", response_model=PositionOrderRead)
def update_position_order(
    session: SessionDep, order_id: int, order_update: PositionOrderUpdate
) -> PositionOrderRead:
    """Update a position order (only allowed if feature flag is enabled)."""
    settings = get_settings()
    if not settings.enable_position_order_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Position order editing is disabled",
        )

    order = session.get(PositionOrder, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position order {order_id} not found",
        )

    # Update fields
    update_data = order_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(order, key, value)

    order.updated_at = datetime.now()

    session.add(order)
    session.commit()
    session.refresh(order)

    return PositionOrderRead.model_validate(order)


@router.delete("/{order_id}")
def delete_position_order(session: SessionDep, order_id: int) -> None:
    """Delete a position order (only allowed if feature flag is enabled)."""
    settings = get_settings()
    if not settings.enable_position_order_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Position order deletion is disabled",
        )

    order = session.get(PositionOrder, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position order {order_id} not found",
        )

    session.delete(order)
    session.commit()


@router.get("/by-position/{position_id}", response_model=list[PositionOrderWithPnL])
def list_position_orders_with_pnl(
    session: SessionDep, position_id: int
) -> list[PositionOrderWithPnL]:
    """Get all orders for a position with calculated PnL."""
    # Get the parent position
    position = session.get(PositionCurrent, position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    # Get all orders for this position
    orders = list(
        session.exec(
            select(PositionOrder).where(PositionOrder.position_id == position_id)
        ).all()
    )

    order_ids = [int(o.id) for o in orders if o.id is not None]
    rp_map = realized_pnl_totals_by_open_order_id(session, order_ids)

    result = []
    for order in orders:
        pnl, pnl_pct = calculate_order_pnl(order, position.mark_price, position.side)
        oid = int(order.id or 0)
        result.append(
            PositionOrderWithPnL(
                **order.model_dump(),
                unrealized_pnl=pnl,
                unrealized_pnl_pct=pnl_pct,
                mark_price=position.mark_price,
                realized_pnl=float(rp_map.get(oid, 0.0)),
            )
        )

    return result
