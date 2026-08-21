"""Neutral data structures for the history-import pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ...db.models import PositionSide

QTY_EPSILON = 1e-9
PRICE_EPSILON = 1e-6


class ImportAction(str, Enum):
    OPEN = "open"
    CLOSE = "close"


class DedupStatus(str, Enum):
    NEW = "new"
    SKIP_EXISTS = "skip_exists"
    CONFLICT = "conflict"
    ORPHAN_CLOSE = "orphan_close"


@dataclass(slots=True)
class NormalizedHistoryOrder:
    """An exchange order reduced to the fields the order ledger needs.

    ``canonical_symbol`` is filled by the fetcher once the symbol mapper has
    resolved ``raw_symbol``; it stays ``None`` for unmapped symbols, which
    blocks commit until the user adds a mapping.
    """

    source_order_id: str
    raw_symbol: str
    side: PositionSide  # long / short
    action: ImportAction
    qty: float
    price: float
    created_at: datetime  # execution time; order update is a low-confidence fallback
    canonical_symbol: Optional[str] = None
    order_placed_at: Optional[datetime] = None  # 委托时间 (display / audit only)
    realized_pnl: Optional[float] = None
    margin_mode: Optional[str] = None
    time_source: str = "trade_fill"  # trade_fill / order_update

    @property
    def group_key(self) -> tuple[str, str]:
        """Position grouping key: ``(canonical_symbol, side)``."""

        return (self.canonical_symbol or self.raw_symbol, self.side.value)


@dataclass(slots=True)
class ClosedPositionSummary:
    """A closed-position row used only to validate the reconstructed ledger."""

    raw_symbol: str
    side: PositionSide
    close_qty: float
    entry_price: float
    close_price: float
    realized_pnl: float
    canonical_symbol: Optional[str] = None
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None


@dataclass(slots=True)
class PlannedMatch:
    """One simulated FIFO slice: an open leg consumed by a close event."""

    open_source_order_id: Optional[str]
    open_local_order_id: Optional[int]
    matched_qty: float
    open_price: float
    close_price: float
    realized_pnl: float


@dataclass(slots=True)
class OrderPreview:
    """Per-order preview row returned to the UI."""

    source_order_id: str
    raw_symbol: str
    canonical_symbol: Optional[str]
    side: str
    action: str
    qty: float
    price: float
    created_at: datetime
    dedup_status: DedupStatus
    order_placed_at: Optional[datetime] = None
    realized_pnl: Optional[float] = None
    time_source: str = "trade_fill"
    matches: list[PlannedMatch] = field(default_factory=list)
    note: Optional[str] = None


@dataclass(slots=True)
class ImportSummary:
    total_fetched: int = 0
    new_opens: int = 0
    new_closes: int = 0
    skipped: int = 0
    conflicts: int = 0
    orphans: int = 0
    pnl_validation_warnings: int = 0
    unresolved_fill_time: int = 0
    filtered_out_of_scope: int = 0
    fallback_time_orders: int = 0


@dataclass(slots=True)
class HistoryFetchStats:
    """Diagnostics that make an empty/partial preview explainable."""

    unresolved_fill_time: int = 0
    filtered_out_of_scope: int = 0
    fallback_time_orders: int = 0
    fetched_orders: int = 0
    fetched_trades: int = 0


@dataclass(slots=True)
class HistoryFetchResult:
    """Fetcher result with diagnostics and backwards-compatible iteration."""

    orders: list[NormalizedHistoryOrder] = field(default_factory=list)
    closed_positions: list[ClosedPositionSummary] = field(default_factory=list)
    stats: HistoryFetchStats = field(default_factory=HistoryFetchStats)

    def __iter__(self):
        # Existing callers unpacked ``orders, closed_positions``.  Keep that
        # API while exposing ``.stats`` to the route and newer callers.
        yield self.orders
        yield self.closed_positions


@dataclass(slots=True)
class ImportPreviewResult:
    orders: list[OrderPreview] = field(default_factory=list)
    closed_positions: list[ClosedPositionSummary] = field(default_factory=list)
    summary: ImportSummary = field(default_factory=ImportSummary)
    blockers: list[str] = field(default_factory=list)
