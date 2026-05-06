"""Snapshot DTOs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import Field

from ..db.models import DataSource, PositionSide
from .common import APIModel


class AccountSnapshotRead(APIModel):
    id: int
    snapshot_date: date
    account_id: int
    asset: str
    total_equity: float
    total_unrealized_pnl: float
    total_available: float
    source: DataSource
    created_at: datetime


class PositionSnapshotRead(APIModel):
    id: int
    snapshot_date: date
    account_id: int
    canonical_symbol: str
    side: PositionSide
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    source: DataSource
    created_at: datetime


class PnlPoint(APIModel):
    snapshot_date: date
    total_equity: float
    total_unrealized_pnl: float


class PnlSeries(APIModel):
    range: str
    asset: str = "USDT"
    points: list[PnlPoint] = Field(default_factory=list)


class ManualBalanceItem(APIModel):
    asset: str
    equity: float
    available: float = 0.0
    frozen: float = 0.0


class ManualPositionItem(APIModel):
    canonical_symbol: str
    side: PositionSide = PositionSide.NET
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float = 0.0


class ManualSnapshotCreate(APIModel):
    account_id: int
    snapshot_date: date
    asset: str = "USDT"
    total_equity: Optional[float] = None
    total_unrealized_pnl: float = 0.0
    total_available: float = 0.0
    balances: list[ManualBalanceItem] = Field(default_factory=list)
    positions: list[ManualPositionItem] = Field(default_factory=list)
    operator: str = "local"


class ManualSnapshotResult(APIModel):
    account_id: int
    snapshot_date: date
    accounts_written: int
    positions_written: int
    balances_written: int


class DailySnapshotResult(APIModel):
    snapshot_date: date
    accounts_written: int
    positions_written: int
    balances_aggregated: int
