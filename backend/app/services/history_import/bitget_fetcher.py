"""Pull + normalise Bitget history into the neutral import structures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ...core.logging import get_logger
from ..exchange.base import ExchangeClient
from ..exchange.ccxt_client import _HISTORY_WINDOW_MS
from ..normalize.symbol_mapper import SymbolMapper
from .normalize_bitget import (
    TradeIndex,
    aggregate_bitget_trades_to_order_raw,
    build_order_trade_index,
    normalize_bitget_closed_position,
    normalize_bitget_order,
)
from .types import ClosedPositionSummary, NormalizedHistoryOrder

_logger = get_logger(__name__)

# Bitget ``fetchClosedOrders`` filters by placement time; look back up to 90 days
# so orders placed before the user's start date but filled inside the window are
# still returned in bulk when possible.
_ORDER_PLACEMENT_LOOKBACK_MS = _HISTORY_WINDOW_MS


def _resolve_canonical(
    mapper: SymbolMapper, exchange_name: str, raw_symbol: str
) -> Optional[str]:
    resolved = mapper.resolve(exchange_name, raw_symbol, instrument_hint="perp")
    return resolved.canonical if resolved is not None else None


def _ms_to_naive_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _fill_time_in_range(fill_time: datetime, since_ms: int, until_ms: int) -> bool:
    since_dt = _ms_to_naive_utc(since_ms)
    until_dt = _ms_to_naive_utc(until_ms)
    return since_dt <= fill_time <= until_dt


def _filter_fill_times(
    fill_times: dict[str, datetime], since_ms: int, until_ms: int
) -> dict[str, datetime]:
    return {
        oid: ft
        for oid, ft in fill_times.items()
        if _fill_time_in_range(ft, since_ms, until_ms)
    }


def _ingest_raw_order(
    by_id: dict[str, NormalizedHistoryOrder],
    raw: dict[str, Any],
    *,
    fill_times: dict[str, datetime],
    mapper: SymbolMapper,
    exchange_name: str,
) -> None:
    source_id = str(
        raw.get("id") or (raw.get("info") or {}).get("orderId") or ""
    )
    if not source_id:
        return
    fill_time = fill_times.get(source_id)
    order = normalize_bitget_order(raw, fill_time=fill_time)
    if order is None:
        return
    order.canonical_symbol = _resolve_canonical(
        mapper, exchange_name, order.raw_symbol
    )
    existing = by_id.get(order.source_order_id)
    if existing is None:
        by_id[order.source_order_id] = order
        return
    if order.realized_pnl is not None and existing.realized_pnl is None:
        by_id[order.source_order_id] = order


def _resolve_missing_orders(
    client: ExchangeClient,
    *,
    by_id: dict[str, NormalizedHistoryOrder],
    fill_times: dict[str, datetime],
    trade_index: TradeIndex,
    mapper: SymbolMapper,
    exchange_name: str,
) -> int:
    """Recover orders visible in fills but absent from closed-order history."""

    missing_ids = sorted(set(fill_times) - set(by_id))
    if not missing_ids:
        return 0

    recovered = 0
    for order_id in missing_ids:
        symbol = trade_index.symbols.get(order_id)
        raw: Optional[dict[str, Any]] = None
        if symbol:
            raw = client.fetch_order(order_id, symbol=symbol)
        if raw is None:
            raw = aggregate_bitget_trades_to_order_raw(
                order_id, trade_index.trades_by_order.get(order_id, [])
            )
        if raw is None:
            _logger.warning(
                "could not resolve order %s (symbol=%s) from trades",
                order_id,
                symbol,
            )
            continue
        before = len(by_id)
        _ingest_raw_order(
            by_id,
            raw,
            fill_times=fill_times,
            mapper=mapper,
            exchange_name=exchange_name,
        )
        if len(by_id) > before:
            recovered += 1

    if recovered:
        _logger.info(
            "recovered %d orders placed before query start via fills/fetch_order",
            recovered,
        )
    return recovered


def fetch_bitget_history(
    client: ExchangeClient,
    mapper: SymbolMapper,
    *,
    exchange_name: str,
    since_ms: int,
    until_ms: int,
) -> tuple[list[NormalizedHistoryOrder], list[ClosedPositionSummary]]:
    """Return normalised orders + closed-position summaries for a time range.

    **Inclusion is by fill time** (``since_ms`` … ``until_ms``). Closed orders
    are queried with an extended placement lookback because Bitget filters
    order history by 委托时间; any order still missing after that is recovered
    from ``fetchMyTrades`` (and optionally ``fetchOrder``).
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
        if isinstance(raw, dict) and raw.get("symbol"):
            discovered_symbols.add(str(raw["symbol"]))

    # Trades drive fill-time inclusion and symbol discovery.
    raw_trades = client.fetch_my_trades_history(
        since=since_ms, until=until_ms, symbols=sorted(discovered_symbols) or None
    )
    trade_index = build_order_trade_index(raw_trades)
    for raw in raw_trades:
        if isinstance(raw, dict) and raw.get("symbol"):
            discovered_symbols.add(str(raw["symbol"]))

    symbols = sorted(discovered_symbols) or None
    fill_times = _filter_fill_times(trade_index.fill_times, since_ms, until_ms)
    if fill_times:
        _logger.info(
            "resolved fill times for %d orders (%d trades) in user window",
            len(fill_times),
            len(raw_trades),
        )

    order_since_ms = max(0, since_ms - _ORDER_PLACEMENT_LOOKBACK_MS)
    raw_orders = client.fetch_closed_orders_history(
        since=order_since_ms, until=until_ms, symbols=symbols
    )

    by_id: dict[str, NormalizedHistoryOrder] = {}
    missing_fill_time = 0
    for raw in raw_orders:
        source_id = str(
            (raw.get("id") if isinstance(raw, dict) else None)
            or (raw.get("info", {}) or {}).get("orderId")
            or ""
        )
        if source_id and source_id not in fill_times:
            missing_fill_time += 1
        _ingest_raw_order(
            by_id,
            raw,
            fill_times=fill_times,
            mapper=mapper,
            exchange_name=exchange_name,
        )

    _resolve_missing_orders(
        client,
        by_id=by_id,
        fill_times=fill_times,
        trade_index=trade_index,
        mapper=mapper,
        exchange_name=exchange_name,
    )

    if missing_fill_time:
        _logger.warning(
            "%d closed orders had no matching trade fill time; "
            "falling back to order update/placement time",
            missing_fill_time,
        )

    # Final guard: only orders whose fill time falls in the user window.
    orders = [
        o
        for o in by_id.values()
        if _fill_time_in_range(o.created_at, since_ms, until_ms)
    ]
    return orders, closed_positions
