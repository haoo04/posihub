"""Position Orders endpoints (order-level position tracking)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..core.config import get_settings
from ..db.models import (
    Account,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
)
from ..schemas.position_order import (
    PositionOrderCreate,
    PositionOrderRead,
    PositionOrderUpdate,
    PositionOrderWithPnL,
)
from ..services.pnl_calculator import (
    base_asset_from_canonical,
    entry_base_to_quote,
    get_quantity_context,
    is_coin_margined_account,
    linear_unrealized_pnl_usdt,
    quote_to_entry_base,
    usdt_to_settlement_coin,
)
from ..services.position_order_close import _refresh_position_fields_from_orders
from ..services.realized_pnl_query import (
    close_price_by_open_order_id,
    realized_pnl_totals_by_open_order_id,
)
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/position-orders", tags=["position-orders"])


def order_read(order: PositionOrder, context: dict[str, str]) -> PositionOrderRead:
    data = order.model_dump()
    if context["quantity_mode"] == "quote_contract":
        data["open_qty"] = entry_base_to_quote(order.open_qty, order.entry_price)
        data["remaining_qty"] = entry_base_to_quote(order.remaining_qty, order.entry_price)
    return PositionOrderRead(**data, **context)


def calculate_order_pnl(
    order: PositionOrder, mark_price: float, side: PositionSide
) -> tuple[float, float]:
    """Calculate unrealized PnL for an order.

    Returns:
        Tuple of (unrealized_pnl_usdt, unrealized_pnl_pct)
    """
    qty = order.remaining_qty
    if qty == 0:
        return 0.0, 0.0

    pnl_usdt = linear_unrealized_pnl_usdt(
        side, order.entry_price, mark_price, qty
    )

    entry_value = order.entry_price * qty
    pnl_pct = (pnl_usdt / entry_value * 100) if entry_value != 0 else 0.0

    return pnl_usdt, pnl_pct


def _build_order_with_pnl(
    order: PositionOrder,
    *,
    position: PositionCurrent,
    account: Account,
    realized_pnl_usdt: float,
    close_price: Optional[float],
    context: dict[str, str],
    realized_pnl_coin: float = 0.0,
) -> PositionOrderWithPnL:
    pnl_usdt, pnl_pct = calculate_order_pnl(
        order, position.mark_price, position.side
    )
    coin = is_coin_margined_account(account.account_type)
    pnl_asset = base_asset_from_canonical(position.canonical_symbol) if coin else None

    unrealized_native: Optional[float] = None
    realized_native: Optional[float] = None
    mark = float(position.mark_price or 0.0)

    if coin:
        unrealized_native = usdt_to_settlement_coin(pnl_usdt, mark)
        realized_native = (
            realized_pnl_coin
            if context["quantity_mode"] == "quote_contract"
            else usdt_to_settlement_coin(realized_pnl_usdt, mark)
        )

    return PositionOrderWithPnL(
        **order_read(order, context).model_dump(),
        unrealized_pnl=pnl_usdt,
        unrealized_pnl_pct=pnl_pct,
        mark_price=position.mark_price,
        realized_pnl=realized_pnl_usdt,
        close_price=close_price,
        pnl_asset=pnl_asset,
        unrealized_pnl_native=unrealized_native,
        unrealized_pnl_usdt=pnl_usdt,
        realized_pnl_native=realized_native,
        realized_pnl_usdt=realized_pnl_usdt,
    )


@router.get("", response_model=list[PositionOrderRead])
def list_position_orders(
    session: SessionDep,
    position_id: Optional[int] = None,
) -> list[PositionOrderRead]:
    """List all position orders, optionally filtered by position_id."""
    query = select(PositionOrder)
    if position_id is not None:
        query = query.where(PositionOrder.position_id == position_id)

    query = query.order_by(
        PositionOrder.created_at.asc(), PositionOrder.id.asc()
    )

    orders = list(session.exec(query).all())
    result = []
    for order in orders:
        position = session.get(PositionCurrent, order.position_id)
        context = get_quantity_context(session, position.account_id, position.canonical_symbol)
        result.append(order_read(order, context))
    return result


@router.get("/{order_id}", response_model=PositionOrderWithPnL)
def get_position_order(session: SessionDep, order_id: int) -> PositionOrderWithPnL:
    """Get a single position order with calculated PnL."""
    order = session.get(PositionOrder, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position order {order_id} not found",
        )

    position = session.get(PositionCurrent, order.position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent position {order.position_id} not found",
        )

    account = session.get(Account, position.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {position.account_id} not found",
        )

    oid = int(order.id or 0)
    rp_map = realized_pnl_totals_by_open_order_id(session, [oid])
    cp_map = close_price_by_open_order_id(session, [oid])
    context = get_quantity_context(session, position.account_id, position.canonical_symbol)
    native_map = (
        realized_pnl_totals_by_open_order_id(session, [oid], settlement_coin=True)
        if context["quantity_mode"] == "quote_contract"
        else {}
    )
    close_px = cp_map.get(oid) if order.status != PositionOrderStatus.OPEN else None

    return _build_order_with_pnl(
        order,
        position=position,
        account=account,
        realized_pnl_usdt=float(rp_map.get(oid, 0.0)),
        close_price=close_px,
        context=context,
        realized_pnl_coin=native_map.get(oid, 0.0),
    )


@router.post("", response_model=PositionOrderRead, status_code=status.HTTP_201_CREATED)
def create_position_order(
    session: SessionDep, order_in: PositionOrderCreate
) -> PositionOrderRead:
    """Create a new position order."""
    position = session.get(PositionCurrent, order_in.position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {order_in.position_id} not found",
        )

    try:
        context = get_quantity_context(
            session, position.account_id, position.canonical_symbol, validate=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = order_in.model_dump()
    if context["quantity_mode"] == "quote_contract":
        data["open_qty"] = quote_to_entry_base(order_in.open_qty, order_in.entry_price)
    order = PositionOrder(
        **data,
        remaining_qty=data["open_qty"],
        status=PositionOrderStatus.OPEN,
    )

    session.add(order)
    if context["quantity_mode"] == "quote_contract":
        session.flush()
        _refresh_position_fields_from_orders(session, position, now=order.updated_at)
        session.add(position)
    session.commit()
    session.refresh(order)

    return order_read(order, context)


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

    update_data = order_update.model_dump(exclude_unset=True)
    position = session.get(PositionCurrent, order.position_id)
    try:
        context = get_quantity_context(
            session, position.account_id, position.canonical_symbol, validate=True
        )
        if any(
            update_data.get(key, 1) is None for key in ("open_qty", "remaining_qty", "entry_price")
        ):
            raise ValueError("Quantity and entry_price cannot be null")
        if context["quantity_mode"] == "quote_contract":
            entry = update_data.get("entry_price", order.entry_price)
            # Preserve contract face value when only the entry price changes.
            for key in ("open_qty", "remaining_qty"):
                if key in update_data or "entry_price" in update_data:
                    old_internal = getattr(order, key)
                    quote_qty = update_data.get(key, old_internal * order.entry_price)
                    internal = quote_to_entry_base(quote_qty, entry)
                    # Saving a normalized legacy API value unchanged must not drift storage.
                    if entry == order.entry_price and quote_qty == entry_base_to_quote(
                        old_internal, entry
                    ):
                        internal = old_internal
                    update_data[key] = internal
        open_qty = update_data.get("open_qty", order.open_qty)
        remaining_qty = update_data.get("remaining_qty", order.remaining_qty)
        if remaining_qty > open_qty + 1e-9:
            raise ValueError("remaining_qty cannot exceed open_qty")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for key, value in update_data.items():
        setattr(order, key, value)

    order.updated_at = datetime.now()

    session.add(order)
    if context["quantity_mode"] == "quote_contract":
        session.flush()
        _refresh_position_fields_from_orders(session, position, now=order.updated_at)
        session.add(position)
    session.commit()
    session.refresh(order)

    return order_read(order, context)


@router.delete("/{order_id}")
def delete_position_order(session: SessionDep, order_id: int) -> None:
    """Delete a position order (only allowed if feature flag is enabled)."""
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

    session.delete(order)
    session.commit()


@router.get("/by-position/{position_id}", response_model=list[PositionOrderWithPnL])
def list_position_orders_with_pnl(
    session: SessionDep, position_id: int
) -> list[PositionOrderWithPnL]:
    """Get all orders for a position with calculated PnL."""
    position = session.get(PositionCurrent, position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    account = session.get(Account, position.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {position.account_id} not found",
        )

    orders = list(
        session.exec(
            select(PositionOrder)
            .where(PositionOrder.position_id == position_id)
            .order_by(PositionOrder.created_at.asc(), PositionOrder.id.asc())
        ).all()
    )

    order_ids = [int(o.id) for o in orders if o.id is not None]
    rp_map = realized_pnl_totals_by_open_order_id(session, order_ids)
    cp_map = close_price_by_open_order_id(session, order_ids)
    context = get_quantity_context(session, position.account_id, position.canonical_symbol)
    native_map = (
        realized_pnl_totals_by_open_order_id(session, order_ids, settlement_coin=True)
        if context["quantity_mode"] == "quote_contract"
        else {}
    )

    result: list[PositionOrderWithPnL] = []
    for order in orders:
        oid = int(order.id or 0)
        close_px = cp_map.get(oid) if order.status != PositionOrderStatus.OPEN else None
        result.append(
            _build_order_with_pnl(
                order,
                position=position,
                account=account,
                realized_pnl_usdt=float(rp_map.get(oid, 0.0)),
                close_price=close_px,
                context=context,
                realized_pnl_coin=native_map.get(oid, 0.0),
            )
        )

    return result
