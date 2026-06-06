"""Performance analytics DTOs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .common import APIModel


class PerformanceScopeRead(APIModel):
    account_ids: list[int]
    exchange_id: Optional[int] = None
    include_simulated: bool = False
    account_count: int = 0


class DataCoverageRead(APIModel):
    snapshot_days: int = 0
    first_snapshot_date: Optional[date] = None
    last_snapshot_date: Optional[date] = None
    trade_count: int = 0
    first_trade_at: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None


class EquityPerformancePoint(APIModel):
    snapshot_date: date
    total_equity: float
    drawdown_pct: float


class EquityPerformanceSeries(APIModel):
    range: str
    asset: str
    period_start: date
    period_end: date
    scope: PerformanceScopeRead
    points: list[EquityPerformancePoint]
    data_coverage: DataCoverageRead


class PerformanceSummary(APIModel):
    range: str
    asset: str
    period_start: date
    period_end: date
    scope: PerformanceScopeRead
    data_coverage: DataCoverageRead

    # Equity track
    equity_start: float = 0.0
    equity_end: float = 0.0
    equity_change: float = 0.0
    equity_change_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    annualized_return_pct: float = 0.0
    calmar_ratio: Optional[float] = None

    # Trade track (close executions)
    realized_pnl_total: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_loss_ratio: Optional[float] = None
    profit_factor: Optional[float] = None
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade_pnl: float = 0.0
    max_win_streak: int = 0
    max_loss_streak: int = 0

    # Live exposure
    unrealized_pnl: float = 0.0
    open_position_count: int = 0


class BreakdownRowRead(APIModel):
    key: str
    label: str
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float
    realized_pnl_total: float
    avg_pnl: float


class PerformanceBreakdown(APIModel):
    range: str
    asset: str
    dimension: str
    period_start: date
    period_end: date
    scope: PerformanceScopeRead
    rows: list[BreakdownRowRead]


class RealizedPnlPoint(APIModel):
    trade_date: date
    realized_pnl: float
    trade_count: int


class RealizedPnlSeries(APIModel):
    range: str
    asset: str
    period_start: date
    period_end: date
    scope: PerformanceScopeRead
    points: list[RealizedPnlPoint]
