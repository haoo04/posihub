"""Tests for trade-driven recovery of pre-window placement orders."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.exchange.base import RawPosition
from app.db.models import AccountType
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


class _ScopeMapper:
    def list_raw_symbols(self, exchange, *, quote_asset=None):
        return set()

    def resolve(self, exchange, raw_symbol, **kwargs):
        if "/USDT" in raw_symbol:
            return type("Resolved", (), {"canonical": "LINK-USDT-PERP"})()
        return type("Resolved", (), {"canonical": "BTC-USD-PERP"})()


class _ScopeClient(_FakeClient):
    pass


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


def test_known_out_of_window_fill_cannot_fallback_to_update_time() -> None:
    since = _ms(2026, 5, 28)
    until = _ms(2026, 5, 31)
    order = {
        "id": "outside-fill",
        "symbol": "ETH/USDT:USDT",
        "filled": 1.0,
        "average": 2_000.0,
        "side": "buy",
        "info": {
            "orderId": "outside-fill",
            "tradeSide": "open",
            "posSide": "long",
            "uTime": str(_ms(2026, 5, 29)),
        },
    }
    trade = {
        "id": "outside-fill-row",
        "order": "outside-fill",
        "symbol": "ETH/USDT:USDT",
        "timestamp": _ms(2026, 5, 20),
        "side": "buy",
        "amount": 1.0,
        "price": 2_000.0,
        "info": {"orderId": "outside-fill", "tradeSide": "open", "posSide": "long"},
    }
    client = _FakeClient(trades=[trade], orders=[order])

    result = fetch_bitget_history(
        client,
        _FakeMapper(),
        exchange_name="bitget",
        since_ms=since,
        until_ms=until,
    )

    assert result.orders == []


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


def test_pre_window_link_order_is_selected_by_fill_time() -> None:
    since = _ms(2026, 8, 20, 4, 40)
    until = _ms(2026, 8, 20, 4, 43)
    placed = _ms(2026, 8, 20, 0, 52)
    filled = _ms(2026, 8, 20, 4, 42) + 22_000
    trade = {
        "id": "fill-link-1",
        "order": "link-order-1",
        "symbol": "LINK/USDT:USDT",
        "timestamp": filled,
        "side": "buy",
        "amount": 1.0,
        "price": 12.5,
        "info": {
            "orderId": "link-order-1",
            "productType": "USDT-FUTURES",
            "tradeSide": "open",
            "posSide": "long",
            "cTime": str(placed),
        },
    }
    order = {
        "id": "link-order-1",
        "symbol": "LINK/USDT:USDT",
        "filled": 1.0,
        "average": 12.5,
        "side": "buy",
        "info": {
            "orderId": "link-order-1",
            "productType": "USDT-FUTURES",
            "tradeSide": "open",
            "posSide": "long",
            "cTime": str(placed),
            "uTime": str(placed),
        },
    }
    client = _ScopeClient(trades=[trade], orders=[order])
    result = fetch_bitget_history(
        client,
        _ScopeMapper(),
        exchange_name="bitget",
        since_ms=since,
        until_ms=until,
        account_type=AccountType.USDT_PERP,
    )

    assert [row.source_order_id for row in result.orders] == ["link-order-1"]
    assert result.orders[0].created_at == datetime.fromtimestamp(
        filled / 1000, tz=timezone.utc
    ).replace(tzinfo=None)
    assert result.orders[0].time_source == "trade_fill"
    assert result.stats.fallback_time_orders == 0


def test_history_filters_other_bitget_product() -> None:
    since = _ms(2026, 8, 20, 4, 40)
    until = _ms(2026, 8, 20, 4, 43)
    usdt_order = {
        "id": "linear-order",
        "symbol": "BTC/USDT:USDT",
        "filled": 1.0,
        "average": 60_000.0,
        "side": "buy",
        "info": {
            "orderId": "linear-order",
            "productType": "USDT-FUTURES",
            "marginCoin": "USDT",
            "tradeSide": "open",
            "posSide": "long",
            "uTime": str(since + 1_000),
        },
    }
    coin_order = {
        "id": "inverse-order",
        "symbol": "BTC/USD:BTC",
        "filled": 1.0,
        "average": 60_000.0,
        "side": "buy",
        "info": {
            "orderId": "inverse-order",
            "productType": "COIN-FUTURES",
            "marginCoin": "BTC",
            "tradeSide": "open",
            "posSide": "long",
            "uTime": str(since + 2_000),
        },
    }
    trades = [
        {
            "id": "linear-fill",
            "order": "linear-order",
            "symbol": "BTC/USDT:USDT",
            "timestamp": since + 1_000,
            "amount": 1.0,
            "price": 60_000.0,
            "side": "buy",
            "info": {
                "orderId": "linear-order",
                "productType": "USDT-FUTURES",
                "tradeSide": "open",
                "posSide": "long",
            },
        },
        {
            "id": "inverse-fill",
            "order": "inverse-order",
            "symbol": "BTC/USD:BTC",
            "timestamp": since + 2_000,
            "amount": 1.0,
            "price": 60_000.0,
            "side": "buy",
            "info": {
                "orderId": "inverse-order",
                "productType": "COIN-FUTURES",
                "tradeSide": "open",
                "posSide": "long",
            },
        },
    ]
    client = _ScopeClient(trades=trades, orders=[usdt_order, coin_order])

    result = fetch_bitget_history(
        client,
        _ScopeMapper(),
        exchange_name="bitget",
        since_ms=since,
        until_ms=until,
        account_type=AccountType.COIN_PERP,
    )

    assert [row.source_order_id for row in result.orders] == ["inverse-order"]
    assert result.orders[0].canonical_symbol == "BTC-USD-PERP"
    assert result.stats.filtered_out_of_scope > 0
