"""Position Order DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import ConfigDict, Field

from ..db.models import DataSource, PositionOrderStatus
from .common import APIModel


class PositionOrderBase(APIModel):
    source: DataSource = DataSource.MANUAL
    source_order_id: Optional[str] = None
    open_qty: float = Field(gt=0, allow_inf_nan=False)
    entry_price: float = Field(gt=0, allow_inf_nan=False)
    leverage: float = 1.0
    margin: Optional[float] = None
    mmr: Optional[float] = None
    liquidation_price: Optional[float] = None


class PositionOrderCreate(PositionOrderBase):
    model_config = ConfigDict(extra="forbid")
    position_id: int


class PositionOrderUpdate(APIModel):
    model_config = ConfigDict(extra="forbid")
    open_qty: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    remaining_qty: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    entry_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    leverage: Optional[float] = None
    margin: Optional[float] = None
    mmr: Optional[float] = None
    liquidation_price: Optional[float] = None
    status: Optional[PositionOrderStatus] = None


class PositionOrderRead(PositionOrderBase):
    quantity_mode: Literal["base", "quote_contract"] = "base"
    quantity_unit: str = ""
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
    realized_pnl: float = 0.0
    close_price: Optional[float] = None
    pnl_asset: Optional[str] = None
    unrealized_pnl_native: Optional[float] = None
    unrealized_pnl_usdt: Optional[float] = None
    realized_pnl_native: Optional[float] = None
    realized_pnl_usdt: Optional[float] = None


class PositionCloseRequest(APIModel):
    """User-initiated FIFO close action against a position."""

    model_config = ConfigDict(extra="forbid")
    close_qty: float = Field(gt=0, allow_inf_nan=False)
    close_price: float = Field(gt=0, allow_inf_nan=False)
    source: DataSource = DataSource.MANUAL
    source_order_id: Optional[str] = None


class SpecifiedCloseLeg(APIModel):
    """One open ``PositionOrder`` slice in a user-specified close."""

    open_order_id: int
    qty: float = Field(gt=0, allow_inf_nan=False)


class SpecifiedCloseRequest(APIModel):
    """User-chosen pairing of open legs for a close of ``close_qty``."""

    model_config = ConfigDict(extra="forbid")
    close_qty: float = Field(gt=0, allow_inf_nan=False)
    close_price: float = Field(gt=0, allow_inf_nan=False)
    legs: list[SpecifiedCloseLeg] = Field(min_length=1)
    source: DataSource = DataSource.MANUAL
    source_order_id: Optional[str] = None


class PositionOrderMatchRead(APIModel):
    id: int
    open_order_id: int
    close_order_id: int
    matched_qty: float
    quantity_mode: Literal["base", "quote_contract"] = "base"
    quantity_unit: str = ""
    open_price: float
    close_price: float
    realized_pnl: float
    matched_at: datetime


class PositionCloseExecutionRead(APIModel):
    id: int
    position_id: int
    close_qty: Optional[float]
    quantity_mode: Literal["base", "quote_contract"] = "base"
    quantity_unit: str = ""
    quantity_warning: Optional[str] = None
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
