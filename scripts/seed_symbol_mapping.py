"""Seed common symbol mappings for popular exchanges.

Usage:

    python -m scripts.seed_symbol_mapping

Safe to re-run: existing rows are updated in-place.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.models import InstrumentType  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.services.normalize.symbol_mapper import (  # noqa: E402
    CanonicalSymbol,
    SymbolMapper,
    make_canonical,
)


SEEDS: list[tuple[str, str, str, str, InstrumentType]] = [
    # exchange, raw_symbol, base, quote, type
    ("binance", "BTC/USDT", "BTC", "USDT", InstrumentType.SPOT),
    ("binance", "ETH/USDT", "ETH", "USDT", InstrumentType.SPOT),
    ("binance", "BTC/USDT:USDT", "BTC", "USDT", InstrumentType.PERP),
    ("binance", "ETH/USDT:USDT", "ETH", "USDT", InstrumentType.PERP),
    ("binance", "BTC/USD:BTC", "BTC", "USD", InstrumentType.PERP),
    ("okx", "BTC/USDT", "BTC", "USDT", InstrumentType.SPOT),
    ("okx", "BTC-USDT-SWAP", "BTC", "USDT", InstrumentType.PERP),
    ("okx", "BTC-USD-SWAP", "BTC", "USD", InstrumentType.PERP),
    ("bybit", "BTC/USDT", "BTC", "USDT", InstrumentType.SPOT),
    ("bybit", "BTC/USDT:USDT", "BTC", "USDT", InstrumentType.PERP),
    ("bybit", "BTC/USD:BTC", "BTC", "USD", InstrumentType.PERP),
    ("bitget", "BTC/USDT", "BTC", "USDT", InstrumentType.SPOT),
    ("bitget", "ETH/USDT", "ETH", "USDT", InstrumentType.SPOT),
    ("bitget", "BTC/USDT:USDT", "BTC", "USDT", InstrumentType.PERP),
    ("bitget", "ETH/USDT:USDT", "ETH", "USDT", InstrumentType.PERP),
    ("bitget", "BTC/USD:BTC", "BTC", "USD", InstrumentType.PERP),
    ("bitget", "ETH/USD:ETH", "ETH", "USD", InstrumentType.PERP),

    # Stock and ETF
    ("bitget", "SPY/USDT:USDT", "SPY", "USDT", InstrumentType.PERP),
]


def main() -> None:
    init_db()
    with session_scope() as session:
        mapper = SymbolMapper(session)
        for exchange, raw, base, quote, instrument in SEEDS:
            canonical = CanonicalSymbol(
                canonical=make_canonical(base, quote, instrument),
                base_asset=base,
                quote_asset=quote,
                instrument_type=instrument,
                contract_size=1.0,
            )
            mapper.upsert_mapping(exchange, raw, canonical)
        print(f"[posihub] seeded {len(SEEDS)} symbol mappings")


if __name__ == "__main__":
    main()
