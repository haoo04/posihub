"""Pull + normalise Bitget history into the neutral import structures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ...core.logging import get_logger
from ...db.models import AccountType
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
from .scope import (
    canonical_matches_bitget_product,
    expected_settlement_asset,
    raw_matches_bitget_product,
)
from .types import (
    ClosedPositionSummary,
    HistoryFetchResult,
    HistoryFetchStats,
    NormalizedHistoryOrder,
)

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


def _raw_symbol(raw: dict[str, Any] | None) -> Optional[str]:
    if not isinstance(raw, dict):
        return None
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    value = raw.get("symbol") or info.get("symbol")
    return str(value) if value else None


def _canonical_in_scope(
    mapper: SymbolMapper,
    exchange_name: str,
    raw_symbol: Optional[str],
    account_type: AccountType | None,
) -> Optional[str]:
    if not raw_symbol:
        return None
    canonical = _resolve_canonical(mapper, exchange_name, raw_symbol)
    # An unmapped symbol remains eligible for preview and is surfaced as the
    # existing mapping blocker.  A known mapping to the other product is not.
    if canonical is not None and not canonical_matches_bitget_product(
        canonical, account_type
    ):
        return "__OUT_OF_SCOPE__"
    return canonical


def _discover_symbols_from_open_positions(client: ExchangeClient) -> set[str]:
    """Seed symbol discovery from **current** open positions.

    Bitget history endpoints require an explicit ``symbol``. Closed-position
    history only lists contracts that fully closed inside the query window, so
    an still-open leg like SPY is omitted and its fills/orders are never
    fetched when other symbols already populated ``discovered_symbols``.
    """

    symbols: set[str] = set()
    try:
        for pos in client.fetch_positions():
            if pos.raw_symbol:
                symbols.add(pos.raw_symbol)
    except Exception as exc:
        _logger.warning("open position symbol discovery skipped: %s", exc)
    if symbols:
        _logger.info(
            "discovered %d symbol(s) from open positions: %s",
            len(symbols),
            ", ".join(sorted(symbols)),
        )
    return symbols


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
    account_type: AccountType | None,
) -> str:
    """Ingest one order and return a diagnostic status."""

    if not raw_matches_bitget_product(raw, account_type):
        return "out_of_scope"
    source_id = str(
        raw.get("id") or (raw.get("info") or {}).get("orderId") or ""
    )
    if not source_id:
        return "invalid"
    fill_time = fill_times.get(source_id)
    order = normalize_bitget_order(raw, fill_time=fill_time)
    if order is None:
        return "invalid"
    canonical = _canonical_in_scope(
        mapper, exchange_name, order.raw_symbol, account_type
    )
    if canonical == "__OUT_OF_SCOPE__":
        return "out_of_scope"
    order.canonical_symbol = canonical
    existing = by_id.get(order.source_order_id)
    if existing is None:
        by_id[order.source_order_id] = order
        return "inserted"
    if order.realized_pnl is not None and existing.realized_pnl is None:
        by_id[order.source_order_id] = order
        return "replaced"
    return "duplicate"


def _resolve_missing_orders(
    client: ExchangeClient,
    *,
    by_id: dict[str, NormalizedHistoryOrder],
    fill_times: dict[str, datetime],
    trade_index: TradeIndex,
    mapper: SymbolMapper,
    exchange_name: str,
    account_type: AccountType | None,
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
        status = _ingest_raw_order(
            by_id,
            raw,
            fill_times=fill_times,
            mapper=mapper,
            exchange_name=exchange_name,
            account_type=account_type,
        )
        if status in {"inserted", "replaced"} or len(by_id) > before:
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
    account_type: AccountType | None = None,
) -> HistoryFetchResult:
    """Return normalised orders + closed-position summaries for a time range.

    **Inclusion is by fill time** (``since_ms`` … ``until_ms``). Closed orders
    are queried with an extended placement lookback because Bitget filters
    order history by 委托时间; any order still missing after that is recovered
    from ``fetchMyTrades`` (and optionally ``fetchOrder``).
    """

    stats = HistoryFetchStats()
    filtered_keys: set[str] = set()

    def mark_filtered(raw: Any, kind: str) -> None:
        if isinstance(raw, dict):
            info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
            if kind == "trade":
                value = raw.get("id") or info.get("tradeId") or info.get("execId")
            elif kind == "order":
                value = raw.get("id") or info.get("orderId")
            else:
                value = raw.get("id") or info.get("positionId") or _raw_symbol(raw)
        else:
            value = str(raw)
        key = f"{kind}:{value or repr(raw)}"
        if key not in filtered_keys:
            filtered_keys.add(key)
            stats.filtered_out_of_scope += 1

    discovered_symbols: set[str] = set()

    # Persisted mappings are an account-independent symbol catalogue.  They
    # are important when the account currently has no open position and the
    # closed-position endpoint returns no row for the selected range.
    list_symbols = getattr(mapper, "list_raw_symbols", None)
    if callable(list_symbols):
        quote = expected_settlement_asset(account_type)
        discovered_symbols.update(
            list_symbols(exchange_name, quote_asset=quote)
        )

    # Current positions are only a supplemental discovery source.  Filter a
    # known mapping to prevent a U-margined position from seeding a coin query.
    for raw_symbol in _discover_symbols_from_open_positions(client):
        canonical = _canonical_in_scope(
            mapper, exchange_name, raw_symbol, account_type
        )
        if canonical == "__OUT_OF_SCOPE__":
            mark_filtered(raw_symbol, "position")
            continue
        discovered_symbols.add(raw_symbol)

    raw_positions = client.fetch_positions_history(since=since_ms, until=until_ms)
    closed_positions: list[ClosedPositionSummary] = []
    for raw in raw_positions:
        if not raw_matches_bitget_product(raw, account_type):
            mark_filtered(raw, "position")
            continue
        summary = normalize_bitget_closed_position(raw)
        if summary is None:
            continue
        canonical = _canonical_in_scope(
            mapper, exchange_name, summary.raw_symbol, account_type
        )
        if canonical == "__OUT_OF_SCOPE__":
            mark_filtered(raw, "position")
            continue
        summary.canonical_symbol = canonical
        closed_positions.append(summary)
        if raw_symbol := _raw_symbol(raw):
            discovered_symbols.add(raw_symbol)

    order_since_ms = max(0, since_ms - _ORDER_PLACEMENT_LOOKBACK_MS)

    # First ask for account-level order history.  Besides recovering orders
    # whose placement predates the range, this discovers symbols before the
    # symbol-scoped trade endpoint is called.
    raw_order_probe = client.fetch_closed_orders_history(
        since=order_since_ms, until=until_ms, symbols=None
    )
    stats.fetched_orders += len(raw_order_probe)
    for raw in raw_order_probe:
        if not raw_matches_bitget_product(raw, account_type):
            mark_filtered(raw, "order")
            continue
        raw_symbol = _raw_symbol(raw)
        canonical = _canonical_in_scope(
            mapper, exchange_name, raw_symbol, account_type
        )
        if canonical == "__OUT_OF_SCOPE__":
            mark_filtered(raw, "order")
            continue
        if raw_symbol:
            discovered_symbols.add(raw_symbol)

    # When no database/open/history row is available, use the exchange's
    # market catalogue as a bounded fallback.  This avoids the CCXT Bitget
    # ``fetchMyTrades(symbol=None)`` exception that used to be swallowed.
    if not discovered_symbols:
        try:
            expected_quote = expected_settlement_asset(account_type)
            for market in client.fetch_markets():
                if market.instrument_type.lower() != "perp":
                    continue
                if expected_quote and market.quote_asset.upper() != expected_quote:
                    continue
                discovered_symbols.add(market.raw_symbol)
        except Exception as exc:
            _logger.warning("history symbol catalogue discovery skipped: %s", exc)

    # Trades drive fill-time inclusion and symbol discovery.
    raw_trades = client.fetch_my_trades_history(
        since=since_ms, until=until_ms, symbols=sorted(discovered_symbols) or None
    )
    stats.fetched_trades = len(raw_trades)
    scoped_trades: list[dict[str, Any]] = []
    for raw in raw_trades:
        if not raw_matches_bitget_product(raw, account_type):
            mark_filtered(raw, "trade")
            continue
        raw_symbol = _raw_symbol(raw)
        canonical = _canonical_in_scope(
            mapper, exchange_name, raw_symbol, account_type
        )
        if canonical == "__OUT_OF_SCOPE__":
            mark_filtered(raw, "trade")
            continue
        scoped_trades.append(raw)
        if raw_symbol:
            discovered_symbols.add(raw_symbol)
    trade_index = build_order_trade_index(scoped_trades)

    symbols = sorted(discovered_symbols) or None
    # Keep all known execution timestamps for final filtering.  Only the
    # in-window subset is eligible for synthetic order recovery; otherwise an
    # order with a known fill just outside the range could fall back to its
    # update time and be imported incorrectly.
    window_fill_times = _filter_fill_times(
        trade_index.fill_times, since_ms, until_ms
    )
    if window_fill_times:
        _logger.info(
            "resolved fill times for %d orders (%d trades) in user window",
            len(window_fill_times),
            len(raw_trades),
        )

    raw_orders = list(raw_order_probe)
    if symbols:
        raw_orders.extend(
            client.fetch_closed_orders_history(
                since=order_since_ms, until=until_ms, symbols=symbols
            )
        )
    stats.fetched_orders += max(0, len(raw_orders) - len(raw_order_probe))

    by_id: dict[str, NormalizedHistoryOrder] = {}
    candidate_order_ids: set[str] = set()
    for raw in raw_orders:
        source_id = str(
            (raw.get("id") if isinstance(raw, dict) else None)
            or (raw.get("info", {}) or {}).get("orderId")
            or ""
        )
        result = _ingest_raw_order(
            by_id,
            raw,
            fill_times=trade_index.fill_times,
            mapper=mapper,
            exchange_name=exchange_name,
            account_type=account_type,
        )
        if result == "out_of_scope":
            mark_filtered(raw, "order")
        elif source_id:
            candidate_order_ids.add(source_id)

    _resolve_missing_orders(
        client,
        by_id=by_id,
        fill_times=window_fill_times,
        trade_index=trade_index,
        mapper=mapper,
        exchange_name=exchange_name,
        account_type=account_type,
    )

    # A missing fill is not automatically fatal: the exchange's filled-order
    # update time is a low-confidence fallback.  Placement time is never used
    # for range inclusion.
    unresolved_ids: set[str] = set()
    for source_id in candidate_order_ids:
        order = by_id.get(source_id)
        if source_id in trade_index.fill_times:
            if order is None:
                unresolved_ids.add(source_id)
            continue
        if (
            order is None
            or order.time_source != "order_update"
            or not _fill_time_in_range(order.created_at, since_ms, until_ms)
        ):
            unresolved_ids.add(source_id)

    # A fill row can exist without any corresponding closed-order row.  The
    # recovery path normally synthesizes it, but count the remaining gap if
    # the trade payload itself was incomplete.
    unresolved_ids.update(
        source_id for source_id in window_fill_times if source_id not in by_id
    )
    stats.unresolved_fill_time = len(unresolved_ids)

    stats.fallback_time_orders = sum(
        1 for order in by_id.values() if order.time_source == "order_update"
    )
    if stats.unresolved_fill_time:
        _logger.warning(
            "%d orders have no usable fill time; placement time is excluded",
            stats.unresolved_fill_time,
        )

    # Final guard: only orders whose fill time falls in the user window.
    orders = [
        o
        for o in by_id.values()
        if _fill_time_in_range(o.created_at, since_ms, until_ms)
    ]
    return HistoryFetchResult(
        orders=orders,
        closed_positions=closed_positions,
        stats=stats,
    )
