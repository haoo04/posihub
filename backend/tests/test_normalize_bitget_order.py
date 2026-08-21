"""Unit tests for Bitget history normalisation (direction parsing, fields)."""

from __future__ import annotations

from app.db.models import PositionSide
from datetime import datetime

from app.services.history_import.normalize_bitget import (
    build_order_fill_times,
    normalize_bitget_closed_position,
    normalize_bitget_order,
    parse_bitget_direction,
)
from app.services.history_import.types import ImportAction


def _order(**info_overrides):
    info = {
        "tradeSide": "open",
        "posSide": "long",
        "marginMode": "isolated",
        "uTime": 1700000000000,
    }
    info.update(info_overrides.pop("info", {}))
    base = {
        "id": "100",
        "symbol": "ETH/USDT:USDT",
        "timestamp": 1700000000000,
        "side": "buy",
        "filled": 1.0,
        "average": 2000.0,
        "reduceOnly": False,
        "info": info,
    }
    base.update(info_overrides)
    return base


def test_parse_hedge_mode_phrases() -> None:
    assert parse_bitget_direction(
        trade_side="open", pos_side="long", side="buy", reduce_only=False
    ) == (ImportAction.OPEN, PositionSide.LONG)
    assert parse_bitget_direction(
        trade_side="close", pos_side="short", side="buy", reduce_only=True
    ) == (ImportAction.CLOSE, PositionSide.SHORT)


def test_parse_one_way_mode_codes() -> None:
    assert parse_bitget_direction(
        trade_side="buy_single", pos_side=None, side="buy", reduce_only=None
    ) == (ImportAction.OPEN, PositionSide.LONG)
    assert parse_bitget_direction(
        trade_side="sell_single", pos_side=None, side="sell", reduce_only=None
    ) == (ImportAction.OPEN, PositionSide.SHORT)
    # Closing a long is a reduce-sell; closing a short is a reduce-buy.
    assert parse_bitget_direction(
        trade_side="reduce_sell_single", pos_side=None, side="sell", reduce_only=None
    ) == (ImportAction.CLOSE, PositionSide.LONG)
    assert parse_bitget_direction(
        trade_side="reduce_buy_single", pos_side=None, side="buy", reduce_only=None
    ) == (ImportAction.CLOSE, PositionSide.SHORT)


def test_parse_reduce_only_fallback() -> None:
    assert parse_bitget_direction(
        trade_side=None, pos_side=None, side="sell", reduce_only=True
    ) == (ImportAction.CLOSE, PositionSide.LONG)
    assert parse_bitget_direction(
        trade_side=None, pos_side=None, side="buy", reduce_only=False
    ) == (ImportAction.OPEN, PositionSide.LONG)


def test_parse_liquidation_is_close() -> None:
    action, side = parse_bitget_direction(
        trade_side="burst_close_long", pos_side="long", side="sell", reduce_only=True
    )
    assert action == ImportAction.CLOSE
    assert side == PositionSide.LONG


def test_normalize_open_order_fields() -> None:
    order = normalize_bitget_order(_order())
    assert order is not None
    assert order.source_order_id == "100"
    assert order.raw_symbol == "ETH/USDT:USDT"
    assert order.side == PositionSide.LONG
    assert order.action == ImportAction.OPEN
    assert order.qty == 1.0
    assert order.price == 2000.0
    assert order.margin_mode == "isolated"
    assert order.realized_pnl is None
    assert order.created_at.year == 2023


def test_normalize_close_order_carries_realized_pnl() -> None:
    raw = _order(
        id="101",
        side="sell",
        average=2100.0,
        reduceOnly=True,
        info={"tradeSide": "close", "posSide": "long", "totalProfits": "100.5"},
    )
    order = normalize_bitget_order(raw)
    assert order is not None
    assert order.action == ImportAction.CLOSE
    assert order.realized_pnl == 100.5


def test_normalize_skips_unfilled_order() -> None:
    raw = _order(filled=0.0, amount=0.0, info={"baseVolume": "0"})
    assert normalize_bitget_order(raw) is None


def _from_ms(ms: int) -> datetime:
    return datetime.utcfromtimestamp(ms / 1000)


def test_build_order_fill_times_uses_latest_trade() -> None:
    trades = [
        {"order": "100", "timestamp": 1700000000000},
        {"order": "100", "timestamp": 1700003600000},
        {"order": "200", "info": {"orderId": "200", "cTime": "1700007200000"}},
    ]
    times = build_order_fill_times(trades)
    assert times["100"] == _from_ms(1700003600000)
    assert times["200"] == _from_ms(1700007200000)


def test_normalize_order_prefers_fill_time_over_placement() -> None:
    placed_ms = 1700000000000
    fill_ms = 1700007200000
    raw = _order(timestamp=placed_ms, info={"cTime": str(placed_ms)})
    fill_time = _from_ms(fill_ms)
    order = normalize_bitget_order(raw, fill_time=fill_time)
    assert order is not None
    assert order.created_at == fill_time
    assert order.order_placed_at == _from_ms(placed_ms)


def test_normalize_closed_position_summary() -> None:
    raw = {
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "entryPrice": 2000.0,
        "info": {
            "holdSide": "long",
            "openAvgPrice": "2000",
            "closeAvgPrice": "2100",
            "closeTotalPos": "1.5",
            "netProfit": "150",
            "cTime": "1700000000000",
            "uTime": "1700001000000",
        },
    }
    summary = normalize_bitget_closed_position(raw)
    assert summary is not None
    assert summary.side == PositionSide.LONG
    assert summary.close_qty == 1.5
    assert summary.entry_price == 2000.0
    assert summary.close_price == 2100.0
    assert summary.realized_pnl == 150.0
