"""Normalise raw Bitget CCXT order / position dicts.

The functions here are pure (no DB, no network) so they can be unit-tested
against the sample payloads captured in ``docs/bitget-export-analysis.json``.
Symbol resolution to a canonical key happens later in the fetcher, where a
``SymbolMapper`` (and therefore a DB session) is available.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ...db.models import PositionSide
from .types import ImportAction, NormalizedHistoryOrder, ClosedPositionSummary


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


def normalize_bitget_order(raw: dict[str, Any]) -> Optional[NormalizedHistoryOrder]:
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

    created_at = (
        _ms_to_naive_utc(raw.get("timestamp"))
        or _ms_to_naive_utc(info.get("cTime"))
        or _ms_to_naive_utc(info.get("uTime"))
    )
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
        realized_pnl=realized_pnl,
        margin_mode=_norm_margin_mode(raw.get("marginMode") or info.get("marginMode")),
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
