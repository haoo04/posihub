"""Position Order DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

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


class PositionCloseRequest(APIModel):
    """User-initiated FIFO close action against a position."""

    close_qty: float
    close_price: float
    source: DataSource = DataSource.MANUAL
    source_order_id: Optional[str] = None


class SpecifiedCloseLeg(APIModel):
    """One open ``PositionOrder`` slice in a user-specified close."""

    open_order_id: int
    qty: float


class SpecifiedCloseRequest(APIModel):
    """User-chosen pairing of open legs for a close of ``close_qty``."""

    close_qty: float
    close_price: float
    legs: list[SpecifiedCloseLeg] = Field(min_length=1)
    source: DataSource = DataSource.MANUAL
    source_order_id: Optional[str] = None


class PositionOrderMatchRead(APIModel):
    id: int
    open_order_id: int
    close_order_id: int
    matched_qty: float
    open_price: float
    close_price: float
    realized_pnl: float
    matched_at: datetime


class PositionCloseExecutionRead(APIModel):
    id: int
    position_id: int
    close_qty: float
    close_price: float
    source: DataSource
    source_order_id: Optional[str] = None
    realized_pnl: float
    created_at: datetime


class FifoCloseResponse(APIModel):
    """Result of a FIFO close action."""

    execution: PositionCloseExecutionRead
    matches: list[PositionOrderMatchRead]
    affected_orders: list[PositionOrderRead]
    realized_pnl: float
