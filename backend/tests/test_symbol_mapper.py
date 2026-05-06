"""Tests for the symbol mapper heuristic and DB whitelist."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from app.db.models import InstrumentType
from app.services.normalize.symbol_mapper import (
    CanonicalSymbol,
    SymbolMapper,
    infer_canonical,
    make_canonical,
)


def test_make_canonical_normalises_case() -> None:
    assert make_canonical("btc", "usdt", "spot") == "BTC-USDT-SPOT"
    assert make_canonical("eth", "usd", InstrumentType.PERP) == "ETH-USD-PERP"


@pytest.mark.parametrize(
    ("raw", "hint", "expected"),
    [
        ("BTC/USDT", None, "BTC-USDT-SPOT"),
        ("BTC/USDT:USDT", None, "BTC-USDT-PERP"),
        ("BTCUSDT", "perp", "BTC-USDT-PERP"),
        ("ETHUSDT", None, "ETH-USDT-SPOT"),
        ("BTC-USD-SWAP", None, "BTC-USD-PERP"),
        ("BTCUSD_PERP", None, "BTC-USD-PERP"),
    ],
)
def test_infer_canonical_known_patterns(
    raw: str, hint: str | None, expected: str
) -> None:
    result = infer_canonical(raw, instrument_hint=hint)
    assert result is not None
    assert result.canonical == expected


def test_infer_canonical_returns_none_for_garbage() -> None:
    assert infer_canonical("???") is None
    assert infer_canonical("") is None


def test_symbol_mapper_db_overrides_heuristic(in_memory_session: Session) -> None:
    mapper = SymbolMapper(in_memory_session)
    canonical = CanonicalSymbol(
        canonical="BTC-USDT-PERP",
        base_asset="BTC",
        quote_asset="USDT",
        instrument_type=InstrumentType.PERP,
        contract_size=1.0,
    )
    mapper.upsert_mapping("binance", "FOO_BAR", canonical)
    in_memory_session.commit()

    fresh = SymbolMapper(in_memory_session)
    resolved = fresh.resolve("binance", "FOO_BAR")
    assert resolved is not None
    assert resolved.canonical == "BTC-USDT-PERP"
    assert resolved.instrument_type == InstrumentType.PERP


def test_symbol_mapper_falls_back_to_heuristic(in_memory_session: Session) -> None:
    mapper = SymbolMapper(in_memory_session)
    resolved = mapper.resolve("binance", "BTC/USDT")
    assert resolved is not None
    assert resolved.canonical == "BTC-USDT-SPOT"
