"""Derive spot ``PositionCurrent`` rows from wallet balances."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ...core.config import get_settings
from ...db.models import DataSource, InstrumentType, PositionSide
from ..exchange.base import ExchangeClient, RawBalance
from ..normalize.normalizer import NormalizedPosition
from ..normalize.symbol_mapper import CanonicalSymbol, SymbolMapper
from .constants import QUOTE_PRIORITY, STABLECOIN_ASSETS


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ccxt_spot_symbol(base: str, quote: str) -> str:
    return f"{base.upper()}/{quote.upper()}"


def _pick_quote(base: str, balance_assets: set[str]) -> str:
    """Choose a quote asset for ``base`` valuation."""

    del base  # reserved for future multi-quote heuristics
    for quote in QUOTE_PRIORITY:
        if quote in balance_assets or quote == "USDT":
            return quote
    return "USDT"


def _spot_unrealized_pnl(entry_price: float, mark_price: float, qty: float) -> float:
    if entry_price <= 0 or mark_price <= 0 or qty <= 0:
        return 0.0
    return (mark_price - entry_price) * qty


def derive_spot_positions(
    *,
    account_id: int,
    exchange_name: str,
    balances: list[RawBalance],
    client: ExchangeClient,
    mapper: SymbolMapper,
    source: DataSource = DataSource.API,
    dust_threshold_usd: Optional[float] = None,
    unmapped: Optional[list[str]] = None,
) -> list[NormalizedPosition]:
    """Build long-only spot positions from non-stablecoin wallet balances."""

    threshold = (
        dust_threshold_usd
        if dust_threshold_usd is not None
        else get_settings().spot_dust_threshold_usd
    )
    now = _utcnow()
    balance_assets = {b.asset.upper() for b in balances if b.equity > 0}

    holdings = [
        b
        for b in balances
        if b.equity > 0 and b.asset.upper() not in STABLECOIN_ASSETS
    ]
    if not holdings:
        return []

    requests: list[tuple[RawBalance, str, str, str]] = []
    for bal in holdings:
        base = bal.asset.upper()
        quote = _pick_quote(base, balance_assets)
        raw_symbol = _ccxt_spot_symbol(base, quote)
        requests.append((bal, base, quote, raw_symbol))

    unique_symbols = sorted({raw for _, _, _, raw in requests})
    prices = client.fetch_last_prices(unique_symbols)

    out: list[NormalizedPosition] = []
    for bal, _base, quote, raw_symbol in requests:
        mark_price = float(prices.get(raw_symbol) or 0.0)
        qty = float(bal.equity)
        notional = qty * mark_price if mark_price > 0 else 0.0
        if threshold > 0 and notional > 0 and notional < threshold:
            continue
        if threshold > 0 and notional == 0 and qty > 0:
            # Unknown price — keep the row so the user sees the holding.
            pass

        canonical = mapper.resolve(
            exchange_name,
            raw_symbol,
            instrument_hint=InstrumentType.SPOT,
            base_hint=bal.asset.upper(),
            quote_hint=quote,
        )
        if canonical is None:
            if unmapped is not None:
                unmapped.append(raw_symbol)
            canonical = CanonicalSymbol(
                canonical=f"{bal.asset.upper()}-{quote}-SPOT",
                base_asset=bal.asset.upper(),
                quote_asset=quote,
                instrument_type=InstrumentType.SPOT,
                contract_size=1.0,
            )

        entry_price = 0.0
        out.append(
            NormalizedPosition(
                account_id=account_id,
                canonical_symbol=canonical.canonical,
                side=PositionSide.LONG,
                qty=qty,
                entry_price=entry_price,
                mark_price=mark_price,
                unrealized_pnl=_spot_unrealized_pnl(entry_price, mark_price, qty),
                leverage=1.0,
                margin_mode=None,
                source=source,
                updated_at=now,
                raw_symbol=raw_symbol,
            )
        )
    return out
