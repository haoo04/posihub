"""Exchange + symbol mapping DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ..db.models import InstrumentType
from .common import APIModel


class ExchangeCreate(APIModel):
    name: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class ExchangeRead(APIModel):
    id: int
    name: str
    enabled: bool
    created_at: datetime


class SymbolMappingCreate(APIModel):
    exchange: str = Field(min_length=1, max_length=64)
    raw_symbol: str = Field(min_length=1, max_length=64)
    canonical_symbol: str = Field(min_length=1, max_length=64)
    base_asset: str = Field(min_length=1, max_length=32)
    quote_asset: str = Field(min_length=1, max_length=32)
    instrument_type: InstrumentType = InstrumentType.SPOT
    contract_size: float = 1.0
    is_active: bool = True


class SymbolMappingRead(SymbolMappingCreate):
    id: int
    created_at: datetime
