"""Normalise raw Bitget CCXT order / position dicts.

The functions here are pure (no DB, no network) so they can be unit-tested
against the sample payloads captured in ``docs/bitget-export-analysis.json``.
Symbol resolution to a canonical key happens later in the fetcher, where a
``SymbolMapper`` (and therefore a DB session) is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ...db.models import PositionSide
from .types import ImportAction, NormalizedHistoryOrder, ClosedPositionSummary


@dataclass(slots=True)
class TradeIndex:
    """Per-order aggregates derived from ``fetchMyTrades`` rows."""

    fill_times: dict[str, datetime] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)
    trades_by_order: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    trade_ids: set[str] = field(default_factory=set)


def _ms_to_naive_utc(value: Any) -> Optional[datetime]:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm_margin_mode(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"crossed", "cross"}:
        return "cross"
    if text in {"isolated", "fixed"}:
        return "isolated"
    return text


def parse_bitget_direction(
    *,
    trade_side: Optional[str],
    pos_side: Optional[str],
    side: Optional[str],
    reduce_only: Optional[bool],
) -> Optional[tuple[ImportAction, PositionSide]]:
    """Resolve ``(action, position_side)`` from Bitget direction fields.

    Handles the unified phrases (``open long`` / ``close short``), the
    one-way-mode codes (``buy_single`` / ``reduce_sell_single`` ...), and a
    ``side`` + ``reduceOnly`` fallback. Returns ``None`` if direction cannot
    be determined.
    """

    trade = str(trade_side or "").strip().lower()
    pos = str(pos_side or "").strip().lower()
    bs = str(side or "").strip().lower()
    text = f"{trade} {pos}"

    is_close = (
        "close" in text
        or "reduce" in trade
        or "burst" in trade
        or "delivery" in trade
        or "offset" in trade
        or "adl" in trade
    )
    is_open = (not is_close) and ("open" in text or trade in {"buy_single", "sell_single"})

    if is_close:
        action = ImportAction.CLOSE
    elif is_open:
        action = ImportAction.OPEN
    elif reduce_only is True:
        action = ImportAction.CLOSE
    elif reduce_only is False:
        action = ImportAction.OPEN
    else:
        return None

    has_long = "long" in text
    has_short = "short" in text
    if has_long and not has_short:
        position_side = PositionSide.LONG
    elif has_short and not has_long:
        position_side = PositionSide.SHORT
    else:
        # One-way mode codes carry the direction in ``trade``.
        if trade in {"buy_single", "reduce_sell_single"}:
            position_side = PositionSide.LONG
        elif trade in {"sell_single", "reduce_buy_single"}:
            position_side = PositionSide.SHORT
        elif bs in {"buy", "sell"}:
            if action == ImportAction.OPEN:
                position_side = PositionSide.LONG if bs == "buy" else PositionSide.SHORT
            else:  # closing a long means selling, closing a short means buying
                position_side = PositionSide.LONG if bs == "sell" else PositionSide.SHORT
        else:
            return None

    return action, position_side


def _trade_fill_timestamp(raw: dict[str, Any]) -> Optional[datetime]:
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    return (
        _ms_to_naive_utc(raw.get("timestamp"))
        or _ms_to_naive_utc(info.get("fillTime"))
        or _ms_to_naive_utc(info.get("cTime"))
    )


def build_order_trade_index(raw_trades: list[dict[str, Any]]) -> TradeIndex:
    """Index trades by order id (fill time, symbol, raw rows).

    FIFO matching must use execution time, not order placement time. When an
    order has multiple partial fills we take the **latest** trade timestamp as
    the point at which that order leg completed.
    """

    index = TradeIndex()
    for raw in raw_trades:
        if not isinstance(raw, dict):
            continue
        info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
        trade_id = raw.get("id") or info.get("tradeId") or info.get("execId")
        if trade_id is not None:
            dedup_key = str(trade_id)
            if dedup_key in index.trade_ids:
                continue
            index.trade_ids.add(dedup_key)
        order_id = raw.get("order") or info.get("orderId")
        if order_id is None:
            continue
        key = str(order_id)
        ts = _trade_fill_timestamp(raw)
        if ts is not None:
            existing = index.fill_times.get(key)
            if existing is None or ts > existing:
                index.fill_times[key] = ts
        symbol = raw.get("symbol") or info.get("symbol")
        if symbol and key not in index.symbols:
            index.symbols[key] = str(symbol)
        index.trades_by_order.setdefault(key, []).append(raw)
    return index


def build_order_fill_times(raw_trades: list[dict[str, Any]]) -> dict[str, datetime]:
    """Backward-compatible wrapper around :func:`build_order_trade_index`."""

    return build_order_trade_index(raw_trades).fill_times


def aggregate_bitget_trades_to_order_raw(
    order_id: str,
    trades: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Synthesize a CCXT-like order dict from fill rows.

    Used when ``fetchClosedOrders`` omits an order because its **placement**
    time precedes the query window, even though its **fill** time falls inside
    the window the user selected.
    """

    if not trades:
        return None

    total_qty = 0.0
    notional = 0.0
    symbol: Optional[str] = None
    side: Optional[str] = None
    trade_side: Optional[str] = None
    pos_side: Optional[str] = None
    reduce_only: Optional[bool] = None
    margin_mode: Optional[str] = None
    realized_pnl = 0.0
    has_close_pnl = False
    earliest_place: Optional[datetime] = None

    for raw in trades:
        if not isinstance(raw, dict):
            continue
        info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
        qty = (
            _to_float(raw.get("amount"))
            or _to_float(info.get("baseVolume"))
            or _to_float(info.get("fillQuantity"))
            or _to_float(info.get("size"))
        )
        price = (
            _to_float(raw.get("price"))
            or _to_float(info.get("price"))
            or _to_float(info.get("fillPrice"))
        )
        if qty is None or qty <= 0 or price is None or price <= 0:
            continue
        total_qty += qty
        notional += qty * price
        symbol = symbol or raw.get("symbol") or info.get("symbol")
        side = side or raw.get("side") or info.get("side")
        trade_side = trade_side or info.get("tradeSide")
        pos_side = pos_side or info.get("posSide") or info.get("holdSide")
        if reduce_only is None and raw.get("reduceOnly") is not None:
            reduce_only = bool(raw.get("reduceOnly"))
        margin_mode = margin_mode or raw.get("marginMode") or info.get("marginMode")
        pnl = _to_float(info.get("profit")) or _to_float(info.get("totalProfits"))
        if pnl is not None:
            realized_pnl += pnl
            has_close_pnl = True
        placed = _ms_to_naive_utc(info.get("cTime"))
        if placed is not None and (earliest_place is None or placed < earliest_place):
            earliest_place = placed

    if total_qty <= 0 or not symbol:
        return None

    avg_price = notional / total_qty
    info: dict[str, Any] = {
        "orderId": order_id,
        "symbol": symbol,
        "tradeSide": trade_side,
        "posSide": pos_side,
        "side": side,
        "baseVolume": total_qty,
        "priceAvg": avg_price,
        "marginMode": margin_mode,
    }
    if earliest_place is not None:
        info["cTime"] = int(earliest_place.timestamp() * 1000)
    if has_close_pnl:
        info["totalProfits"] = realized_pnl

    return {
        "id": order_id,
        "symbol": symbol,
        "side": side,
        "filled": total_qty,
        "average": avg_price,
        "reduceOnly": reduce_only,
        "marginMode": margin_mode,
        "info": info,
    }


def normalize_bitget_order(
    raw: dict[str, Any],
    *,
    fill_time: Optional[datetime] = None,
) -> Optional[NormalizedHistoryOrder]:
    """Convert a CCXT Bitget order dict into a :class:`NormalizedHistoryOrder`.

    Returns ``None`` for unfilled / undeterminable orders so callers can skip
    them. ``canonical_symbol`` is left unset for the fetcher to resolve.
    """

    if not isinstance(raw, dict):
        return None
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}

    source_order_id = raw.get("id") or info.get("orderId")
    if source_order_id is None:
        return None
    source_order_id = str(source_order_id)

    symbol = raw.get("symbol") or info.get("symbol")
    if not symbol:
        return None

    qty = _to_float(raw.get("filled"))
    if qty is None or qty == 0:
        qty = _to_float(raw.get("amount")) or _to_float(info.get("baseVolume")) or _to_float(
            info.get("size")
        )
    if qty is None or qty <= 0:
        return None

    price = (
        _to_float(raw.get("average"))
        or _to_float(info.get("priceAvg"))
        or _to_float(raw.get("price"))
    )
    if price is None or price <= 0:
        return None

    direction = parse_bitget_direction(
        trade_side=info.get("tradeSide") or info.get("posSide"),
        pos_side=info.get("posSide") or info.get("holdSide"),
        side=raw.get("side") or info.get("side"),
        reduce_only=raw.get("reduceOnly"),
    )
    if direction is None:
        return None
    action, position_side = direction

    order_placed_at = (
        _ms_to_naive_utc(info.get("cTime"))
        or _ms_to_naive_utc(raw.get("timestamp"))
    )
    # ``created_at`` is the FIFO sort key.  Placement time is deliberately not
    # a fallback: an order can be placed before the requested range and fill
    # inside it.  An order update is retained only as an explicitly marked,
    # low-confidence fallback when the fill endpoint did not return a row.
    update_time = _ms_to_naive_utc(info.get("uTime")) or _ms_to_naive_utc(
        raw.get("lastTradeTimestamp")
    )
    created_at = fill_time or update_time
    if created_at is None:
        return None

    realized_pnl = None
    if action == ImportAction.CLOSE:
        realized_pnl = (
            _to_float(info.get("totalProfits"))
            or _to_float(info.get("pnl"))
            or _to_float(info.get("netProfit"))
        )

    return NormalizedHistoryOrder(
        source_order_id=source_order_id,
        raw_symbol=str(symbol),
        side=position_side,
        action=action,
        qty=qty,
        price=price,
        created_at=created_at,
        order_placed_at=order_placed_at,
        realized_pnl=realized_pnl,
        margin_mode=_norm_margin_mode(raw.get("marginMode") or info.get("marginMode")),
        time_source="trade_fill" if fill_time is not None else "order_update",
    )


def normalize_bitget_closed_position(
    raw: dict[str, Any],
) -> Optional[ClosedPositionSummary]:
    """Convert a CCXT Bitget closed-position dict into a validation summary."""

    if not isinstance(raw, dict):
        return None
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}

    symbol = raw.get("symbol") or info.get("symbol")
    if not symbol:
        return None

    hold_side = str(raw.get("side") or info.get("holdSide") or "").strip().lower()
    if hold_side == "long":
        side = PositionSide.LONG
    elif hold_side == "short":
        side = PositionSide.SHORT
    else:
        side = PositionSide.NET

    close_qty = (
        _to_float(info.get("closeTotalPos"))
        or _to_float(raw.get("contracts"))
        or _to_float(info.get("openTotalPos"))
        or 0.0
    )
    entry_price = _to_float(raw.get("entryPrice")) or _to_float(info.get("openAvgPrice")) or 0.0
    close_price = (
        _to_float(info.get("closeAvgPrice"))
        or _to_float(raw.get("markPrice"))
        or 0.0
    )
    realized_pnl = (
        _to_float(info.get("netProfit"))
        or _to_float(info.get("pnl"))
        or _to_float(raw.get("realizedPnl"))
        or 0.0
    )

    return ClosedPositionSummary(
        raw_symbol=str(symbol),
        side=side,
        close_qty=close_qty,
        entry_price=entry_price,
        close_price=close_price,
        realized_pnl=realized_pnl,
        open_time=_ms_to_naive_utc(info.get("cTime") or raw.get("timestamp")),
        close_time=_ms_to_naive_utc(info.get("uTime")),
    )
