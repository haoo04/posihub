"""Pull + normalise Bitget history into the neutral import structures."""

from __future__ import annotations

from typing import Any, Optional

from ...core.logging import get_logger
from ..exchange.base import ExchangeClient
from ..normalize.symbol_mapper import SymbolMapper
from .normalize_bitget import normalize_bitget_closed_position, normalize_bitget_order
from .types import ClosedPositionSummary, NormalizedHistoryOrder

_logger = get_logger(__name__)


def _resolve_canonical(
    mapper: SymbolMapper, exchange_name: str, raw_symbol: str
) -> Optional[str]:
    resolved = mapper.resolve(exchange_name, raw_symbol, instrument_hint="perp")
    return resolved.canonical if resolved is not None else None


def fetch_bitget_history(
    client: ExchangeClient,
    mapper: SymbolMapper,
    *,
    exchange_name: str,
    since_ms: int,
    until_ms: int,
) -> tuple[list[NormalizedHistoryOrder], list[ClosedPositionSummary]]:
    """Return normalised orders + closed-position summaries for a time range.

    Closed positions drive symbol discovery (and serve as PnL validation),
    then closed orders are pulled per discovered symbol. API duplicates are
    collapsed by ``source_order_id``; the close record (which carries realized
    PnL) wins over a bare fill if both arrive.
    """

    raw_positions = client.fetch_positions_history(since=since_ms, until=until_ms)
    closed_positions: list[ClosedPositionSummary] = []
    discovered_symbols: set[str] = set()
    for raw in raw_positions:
        summary = normalize_bitget_closed_position(raw)
        if summary is None:
            continue
        summary.canonical_symbol = _resolve_canonical(
            mapper, exchange_name, summary.raw_symbol
        )
        closed_positions.append(summary)
        if isinstance(raw, dict):
            sym = raw.get("symbol")
            if sym:
                discovered_symbols.add(str(sym))

    symbols = sorted(discovered_symbols) or None
    raw_orders = client.fetch_closed_orders_history(
        since=since_ms, until=until_ms, symbols=symbols
    )

    by_id: dict[str, NormalizedHistoryOrder] = {}
    for raw in raw_orders:
        order = normalize_bitget_order(raw)
        if order is None:
            continue
        order.canonical_symbol = _resolve_canonical(
            mapper, exchange_name, order.raw_symbol
        )
        existing = by_id.get(order.source_order_id)
        if existing is None:
            by_id[order.source_order_id] = order
            continue
        # Prefer the close record carrying realized PnL.
        if order.realized_pnl is not None and existing.realized_pnl is None:
            by_id[order.source_order_id] = order

    return list(by_id.values()), closed_positions
