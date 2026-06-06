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

__all__ = [
    "BreakdownRow",
    "EquityMetrics",
    "PerformanceScope",
    "RealizedPoint",
    "TradeMetrics",
    "compute_breakdown",
    "compute_equity_metrics",
    "compute_realized_series",
    "compute_trade_metrics",
    "resolve_performance_scope",
]
