"""Trading performance analytics."""

from .breakdown import (
    BreakdownRow,
    RealizedPoint,
    compute_breakdown,
    compute_realized_series,
)
from .equity_metrics import EquityMetrics, compute_equity_metrics
from .scope import PerformanceScope, resolve_performance_scope
from .trade_metrics import TradeMetrics, compute_trade_metrics
from .trades import TradeRow, TradesResult, list_trades

__all__ = [
    "BreakdownRow",
    "EquityMetrics",
    "PerformanceScope",
    "RealizedPoint",
    "TradeMetrics",
    "TradeRow",
    "TradesResult",
    "compute_breakdown",
    "compute_equity_metrics",
    "compute_realized_series",
    "compute_trade_metrics",
    "list_trades",
    "resolve_performance_scope",
]
