"""Position DTOs (current + aggregated views)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from ..db.models import DataSource, PositionSide
from .common import APIModel


class PositionRead(APIModel):
    id: int
    account_id: int
    canonical_symbol: str
    side: PositionSide
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    leverage: float
    margin_mode: Optional[str] = None
    updated_at: datetime
    source: DataSource
    account_type: Optional[str] = None
    pnl_asset: Optional[str] = None


class PositionMerged(APIModel):
    canonical_symbol: str
    side: PositionSide
    qty: float
    avg_entry_price: float
    mark_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    notional: float
    accounts: list[int] = Field(default_factory=list)


PositionView = Literal["split", "merged"]
