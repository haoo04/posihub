"""Overview / dashboard DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .common import APIModel


class OverviewResponse(APIModel):
    total_equity: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_positions: int = 0
    total_accounts: int = 0
    last_snapshot_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
