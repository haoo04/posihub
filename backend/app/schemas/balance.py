"""Account balance DTOs."""

from __future__ import annotations

from datetime import datetime

from ..db.models import DataSource
from .common import APIModel


class BalanceRead(APIModel):
    id: int
    account_id: int
    asset: str
    equity: float
    available: float
    frozen: float
    updated_at: datetime
    source: DataSource
