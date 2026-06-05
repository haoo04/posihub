"""Tests for trade-driven recovery of pre-window placement orders."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.history_import.bitget_fetcher import fetch_bitget_history
from app.services.history_import.normalize_bitget import (
    aggregate_bitget_trades_to_order_raw,
    build_order_trade_index,
)
from app.services.history_import.types import ImportAction


def _ms(y, m, d, h=0, mi=0) -> int:
    return int(datetime(y, m, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


class _FakeClient:
    exchange_name = "bitget"

    def __init__(self, *, trades, orders):
        self._trades = trades
        self._orders = orders
        self.closed_since: int | None = None

    def fetch_positions_history(self, **kwargs):
        return []

    def fetch_my_trades_history(self, **kwargs):
        return self._trades

    def fetch_closed_orders_history(self, *, since, until, symbols=None):
        self.closed_since = since
        return self._orders

    def fetch_order(self, order_id, *, symbol):
        return None

    def close(self):
        pass


class _FakeMapper:
    def resolve(self, exchange, raw_symbol, **kwargs):
        return None


def test_aggregate_trades_builds_order_raw() -> None:
    trades = [
        {
            "order": "9001",
            "symbol": "ETH/USDT:USDT",
            "timestamp": _ms(2026, 5, 29, 10),
            "side": "buy",
            "amount": 0.5,
            "price": 2000.0,
            "info": {"tradeSide": "open", "posSide": "long"},
        },
        {
            "order": "9001",
            "symbol": "ETH/USDT:USDT",
            "timestamp": _ms(2026, 5, 29, 10, 5),
            "side": "buy",
            "amount": 0.5,
            "price": 2100.0,
            "info": {"tradeSide": "open", "posSide": "long"},
        },
    ]
    raw = aggregate_bitget_trades_to_order_raw("9001", trades)
    assert raw is not None
    assert raw["filled"] == 1.0
    assert raw["average"] == 2050.0


def test_fetcher_recovers_order_missing_from_closed_history() -> None:
    since = _ms(2026, 5, 28)
    until = _ms(2026, 5, 31)
    placed_before = _ms(2026, 5, 20)
    filled_after = _ms(2026, 5, 29, 12)

    trades = [
        {
            "order": "9001",
            "symbol": "ETH/USDT:USDT",
            "timestamp": filled_after,
            "side": "buy",
            "amount": 1.0,
            "price": 2500.0,
            "info": {
                "orderId": "9001",
                "tradeSide": "open",
                "posSide": "long",
                "cTime": str(placed_before),
            },
        }
    ]
    # Closed-order API returns nothing (placement before since).
    client = _FakeClient(trades=trades, orders=[])
    orders, _ = fetch_bitget_history(
        client,
        _FakeMapper(),
        exchange_name="bitget",
        since_ms=since,
        until_ms=until,
    )
    assert len(orders) == 1
    assert orders[0].source_order_id == "9001"
    assert orders[0].action == ImportAction.OPEN
    assert orders[0].created_at == datetime(2026, 5, 29, 12, tzinfo=timezone.utc).replace(
        tzinfo=None
    )
    assert client.closed_since == since - 90 * 24 * 60 * 60 * 1000


def test_fetcher_excludes_fills_outside_user_window() -> None:
    since = _ms(2026, 5, 28)
    until = _ms(2026, 5, 31)
    trades = [
        {
            "order": "old",
            "symbol": "ETH/USDT:USDT",
            "timestamp": _ms(2026, 5, 20),
            "side": "buy",
            "amount": 1.0,
            "price": 2000.0,
            "info": {"tradeSide": "open", "posSide": "long"},
        },
        {
            "order": "new",
            "symbol": "ETH/USDT:USDT",
            "timestamp": _ms(2026, 5, 29),
            "side": "buy",
            "amount": 1.0,
            "price": 2100.0,
            "info": {"tradeSide": "open", "posSide": "long"},
        },
    ]
    client = _FakeClient(trades=trades, orders=[])
    orders, _ = fetch_bitget_history(
        client,
        _FakeMapper(),
        exchange_name="bitget",
        since_ms=since,
        until_ms=until,
    )
    assert len(orders) == 1
    assert orders[0].source_order_id == "new"


def test_trade_index_maps_symbols_for_recovery() -> None:
    trades = [
        {
            "order": "42",
            "symbol": "BTC/USDT:USDT",
            "timestamp": _ms(2026, 5, 29),
            "amount": 0.1,
            "price": 60000.0,
            "info": {"tradeSide": "open", "posSide": "long"},
        }
    ]
    index = build_order_trade_index(trades)
    assert index.symbols["42"] == "BTC/USDT:USDT"
    assert "42" in index.trades_by_order
