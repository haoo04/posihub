"""Tests for trade-driven recovery of pre-window placement orders."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.exchange.base import RawPosition
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

    def __init__(
        self,
        *,
        trades,
        orders,
        open_positions: list[RawPosition] | None = None,
        closed_position_symbols: list[str] | None = None,
        trades_by_symbol: dict[str, list[dict]] | None = None,
    ):
        self._trades = trades
        self._orders = orders
        self._open_positions = open_positions or []
        self._closed_position_symbols = closed_position_symbols or []
        self._trades_by_symbol = trades_by_symbol or {}
        self.closed_since: int | None = None
        self.trade_symbols_queried: list[str] | None = None

    def fetch_positions(self):
        return self._open_positions

    def fetch_positions_history(self, **kwargs):
        return [{"symbol": sym} for sym in self._closed_position_symbols]

    def fetch_my_trades_history(self, *, since, until, symbols=None):
        self.trade_symbols_queried = symbols
        if self._trades_by_symbol and symbols:
            out: list[dict] = []
            for sym in symbols:
                out.extend(self._trades_by_symbol.get(sym, []))
            return out
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


def test_open_position_symbol_included_when_closed_history_has_other_symbols() -> None:
    """SPY still open: must fetch SPY fills even if only ETH closed in range."""

    since = _ms(2026, 5, 26)
    until = _ms(2026, 6, 6)
    spy_trade = {
        "order": "spy-open",
        "symbol": "SPY/USDT:USDT",
        "timestamp": _ms(2026, 5, 30, 8),
        "side": "buy",
        "amount": 0.29,
        "price": 676.0,
        "info": {
            "orderId": "spy-open",
            "tradeSide": "open",
            "posSide": "long",
            "cTime": str(_ms(2026, 5, 24)),
        },
    }
    client = _FakeClient(
        trades=[],
        orders=[],
        open_positions=[
            RawPosition(
                raw_symbol="SPY/USDT:USDT",
                side="long",
                qty=0.29,
                entry_price=676.0,
                mark_price=680.0,
                unrealized_pnl=1.0,
            )
        ],
        closed_position_symbols=["ETH/USDT:USDT"],
        trades_by_symbol={"SPY/USDT:USDT": [spy_trade]},
    )
    orders, _ = fetch_bitget_history(
        client,
        _FakeMapper(),
        exchange_name="bitget",
        since_ms=since,
        until_ms=until,
    )
    assert client.trade_symbols_queried is not None
    assert "SPY/USDT:USDT" in client.trade_symbols_queried
    assert len(orders) == 1
    assert orders[0].source_order_id == "spy-open"
    assert orders[0].raw_symbol == "SPY/USDT:USDT"


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
