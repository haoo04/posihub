"""History-import (API backfill) DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .common import APIModel


class HistoryImportPreviewRequest(APIModel):
    """Time range to pull from the exchange (interpreted as UTC if naive)."""

    since: datetime
    until: datetime


class PlannedMatchRead(APIModel):
    open_source_order_id: Optional[str] = None
    open_local_order_id: Optional[int] = None
    matched_qty: float
    open_price: float
    close_price: float
    realized_pnl: float


class OrderPreviewRead(APIModel):
    source_order_id: str
    raw_symbol: str
    canonical_symbol: Optional[str] = None
    side: str
    action: str
    qty: float
    price: float
    created_at: datetime
    dedup_status: str
    realized_pnl: Optional[float] = None
    matches: list[PlannedMatchRead] = []
    note: Optional[str] = None


class ClosedPositionSummaryRead(APIModel):
    raw_symbol: str
    canonical_symbol: Optional[str] = None
    side: str
    close_qty: float
    entry_price: float
    close_price: float
    realized_pnl: float
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None


class ImportSummaryRead(APIModel):
    total_fetched: int = 0
    new_opens: int = 0
    new_closes: int = 0
    skipped: int = 0
    conflicts: int = 0
    orphans: int = 0
    pnl_validation_warnings: int = 0


class HistoryImportPreviewResponse(APIModel):
    preview_id: str
    account_id: int
    fetched_at: datetime
    orders: list[OrderPreviewRead] = []
    closed_positions: list[ClosedPositionSummaryRead] = []
    summary: ImportSummaryRead
    blockers: list[str] = []


class HistoryImportCommitRequest(APIModel):
    preview_id: str


class HistoryImportCommitResponse(APIModel):
    account_id: int
    created_opens: int = 0
    created_closes: int = 0
    skipped: int = 0
    conflicts: int = 0
    orphans: int = 0
