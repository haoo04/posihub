"""Symbol normalisation.

Converts exchange-specific raw symbols (``BTC/USDT``, ``BTCUSDT``,
``BTC/USDT:USDT``, ``BTCUSD_PERP`` ...) into the canonical key

    ``{BASE}-{QUOTE}-{INSTRUMENT_TYPE}``

Examples (canonical):
    ``BTC-USDT-SPOT``, ``BTC-USDT-PERP``, ``BTC-USD-PERP``.

The mapping logic is split in two layers:

1. A heuristic parser :func:`infer_canonical` works on raw CCXT-style strings
   and is used to bootstrap mappings when no explicit row exists.
2. A persisted whitelist (:class:`SymbolMapping`) overrides the heuristic for
   ambiguous cases, exposed via :class:`SymbolMapper`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, select

from ...db.models import InstrumentType, SymbolMapping


_KNOWN_QUOTES = (
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "DAI",
    "USD",
    "EUR",
    "BTC",
    "ETH",
    "BNB",
)


@dataclass(slots=True, frozen=True)
class CanonicalSymbol:
    canonical: str
    base_asset: str
    quote_asset: str
    instrument_type: InstrumentType
    contract_size: float = 1.0


def _to_instrument(value: str | InstrumentType | None) -> InstrumentType:
    if isinstance(value, InstrumentType):
        return value
    if not value:
        return InstrumentType.SPOT
    text = value.lower()
    if text in {"swap", "perp", "perpetual"}:
        return InstrumentType.PERP
    if text in {"future", "futures", "delivery"}:
        return InstrumentType.FUTURES
    return InstrumentType.SPOT


def make_canonical(
    base: str, quote: str, instrument: str | InstrumentType | None
) -> str:
    """Build the canonical key string."""

    inst = _to_instrument(instrument)
    return f"{base.upper()}-{quote.upper()}-{inst.value.upper()}"


def _split_concat(symbol: str) -> Optional[tuple[str, str]]:
    """Split a concatenated symbol like ``BTCUSDT`` into ``(BTC, USDT)``."""

    upper = symbol.upper()
    for quote in _KNOWN_QUOTES:
        if upper.endswith(quote) and len(upper) > len(quote):
            return upper[: -len(quote)], quote
    return None


def infer_canonical(
    raw_symbol: str,
    *,
    instrument_hint: str | InstrumentType | None = None,
    base_hint: Optional[str] = None,
    quote_hint: Optional[str] = None,
    contract_size: float = 1.0,
) -> Optional[CanonicalSymbol]:
    """Best-effort heuristic parser.

    Returns ``None`` if the symbol cannot be confidently parsed; callers
    should then fall back to the persisted whitelist.
    """

    if not raw_symbol:
        return None

    cleaned = raw_symbol.strip().upper()
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    instrument = _to_instrument(instrument_hint)
    base = base_hint.upper() if base_hint else ""
    quote = quote_hint.upper() if quote_hint else ""

    # CCXT style ``BASE/QUOTE`` or ``BASE/QUOTE:SETTLE``
    if "/" in cleaned:
        head, settle = (cleaned.split(":", 1) + [""])[:2]
        try:
            b, q = head.split("/")
        except ValueError:
            return None
        base = base or b
        quote = quote or q
        if settle:
            instrument = InstrumentType.PERP if instrument == InstrumentType.SPOT else instrument
    else:
        # Strip well known suffixes
        token = cleaned
        if token.endswith("-PERP") or token.endswith("PERP"):
            token = token.replace("-PERP", "").replace("PERP", "")
            instrument = InstrumentType.PERP
        if token.endswith("-SWAP") or token.endswith("SWAP"):
            token = token.replace("-SWAP", "").replace("SWAP", "")
            instrument = InstrumentType.PERP

        if "-" in token:
            parts = [p for p in token.split("-") if p]
            if len(parts) >= 2:
                base = base or parts[0]
                quote = quote or parts[1]
                if len(parts) >= 3:
                    instrument = _to_instrument(parts[2])
        else:
            split = _split_concat(token)
            if split is None:
                return None
            base, quote = base or split[0], quote or split[1]

    if not base or not quote:
        return None

    return CanonicalSymbol(
        canonical=make_canonical(base, quote, instrument),
        base_asset=base,
        quote_asset=quote,
        instrument_type=instrument,
        contract_size=contract_size,
    )


class SymbolMapper:
    """Resolves canonical symbols using DB whitelist + heuristic fallback."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._cache: dict[tuple[str, str], SymbolMapping] = {}

    def _lookup_db(self, exchange: str, raw_symbol: str) -> Optional[SymbolMapping]:
        key = (exchange.lower(), raw_symbol)
        if key in self._cache:
            return self._cache[key]
        stmt = select(SymbolMapping).where(
            SymbolMapping.exchange == exchange.lower(),
            SymbolMapping.raw_symbol == raw_symbol,
            SymbolMapping.is_active == True,  # noqa: E712
        )
        row = self._session.exec(stmt).first()
        if row is not None:
            self._cache[key] = row
        return row

    def resolve(
        self,
        exchange: str,
        raw_symbol: str,
        *,
        instrument_hint: str | InstrumentType | None = None,
        base_hint: Optional[str] = None,
        quote_hint: Optional[str] = None,
        contract_size: float = 1.0,
    ) -> Optional[CanonicalSymbol]:
        row = self._lookup_db(exchange, raw_symbol)
        if row is not None:
            return CanonicalSymbol(
                canonical=row.canonical_symbol,
                base_asset=row.base_asset,
                quote_asset=row.quote_asset,
                instrument_type=row.instrument_type,
                contract_size=row.contract_size,
            )
        return infer_canonical(
            raw_symbol,
            instrument_hint=instrument_hint,
            base_hint=base_hint,
            quote_hint=quote_hint,
            contract_size=contract_size,
        )

    def upsert_mapping(
        self,
        exchange: str,
        raw_symbol: str,
        canonical: CanonicalSymbol,
    ) -> SymbolMapping:
        existing = self._lookup_db(exchange, raw_symbol)
        if existing is not None:
            existing.canonical_symbol = canonical.canonical
            existing.base_asset = canonical.base_asset
            existing.quote_asset = canonical.quote_asset
            existing.instrument_type = canonical.instrument_type
            existing.contract_size = canonical.contract_size
            existing.is_active = True
            self._session.add(existing)
            return existing

        row = SymbolMapping(
            exchange=exchange.lower(),
            raw_symbol=raw_symbol,
            canonical_symbol=canonical.canonical,
            base_asset=canonical.base_asset,
            quote_asset=canonical.quote_asset,
            instrument_type=canonical.instrument_type,
            contract_size=canonical.contract_size,
        )
        self._session.add(row)
        self._cache[(exchange.lower(), raw_symbol)] = row
        return row
