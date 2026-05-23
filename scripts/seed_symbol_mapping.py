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


# CCXT-style USDT spot + linear perp for major alts (binance / bybit / bitget / okx).
_USDT_MARGIN_BASES = (
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "LINK",
    "DOT",
    "LTC",
    "TRX",
    "SHIB",
    "UNI",
    "ATOM",
    "NEAR",
    "APT",
    "ARB",
    "OP",
    "SUI",
    "BCH",
    "FIL",
    "TON",
    "PEPE",
    "WLD",
    "INJ",
    "TIA",
    "SEI",
)


def _usdt_margin_seeds() -> list[tuple[str, str, str, str, InstrumentType]]:
    rows: list[tuple[str, str, str, str, InstrumentType]] = []
    for base in _USDT_MARGIN_BASES:
        for exchange in ("binance", "bybit", "bitget"):
            rows.append((exchange, f"{base}/USDT", base, "USDT", InstrumentType.SPOT))
            rows.append(
                (exchange, f"{base}/USDT:USDT", base, "USDT", InstrumentType.PERP)
            )
        rows.append(("okx", f"{base}/USDT", base, "USDT", InstrumentType.SPOT))
        rows.append(("okx", f"{base}-USDT-SWAP", base, "USDT", InstrumentType.PERP))
    return rows


SEEDS: list[tuple[str, str, str, str, InstrumentType]] = [
    *_usdt_margin_seeds(),
    # Coin-margined (inverse) perps
    ("binance", "BTC/USD:BTC", "BTC", "USD", InstrumentType.PERP),
    ("okx", "BTC-USD-SWAP", "BTC", "USD", InstrumentType.PERP),
    ("bybit", "BTC/USD:BTC", "BTC", "USD", InstrumentType.PERP),
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
