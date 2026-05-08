"""Position Order DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..db.models import DataSource, PositionOrderStatus
from .common import APIModel


class PositionOrderBase(APIModel):
    source: DataSource = DataSource.MANUAL
    source_order_id: Optional[str] = None
    open_qty: float
    entry_price: float
    leverage: float = 1.0
    margin: Optional[float] = None
    mmr: Optional[float] = None
    liquidation_price: Optional[float] = None


class PositionOrderCreate(PositionOrderBase):
    position_id: int


class PositionOrderUpdate(APIModel):
    open_qty: Optional[float] = None
    remaining_qty: Optional[float] = None
    entry_price: Optional[float] = None
    leverage: Optional[float] = None
    margin: Optional[float] = None
    mmr: Optional[float] = None
    liquidation_price: Optional[float] = None
    status: Optional[PositionOrderStatus] = None


class PositionOrderRead(PositionOrderBase):
    id: int
    position_id: int
    status: PositionOrderStatus
    remaining_qty: float
    created_at: datetime
    updated_at: datetime


class PositionOrderWithPnL(PositionOrderRead):
    """Position order with calculated unrealized PnL."""
    unrealized_pnl: float
    unrealized_pnl_pct: float
    mark_price: float
