"""Pagination, product-param, and duplicate protections for Bitget history."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.exchange.ccxt_client import CcxtExchangeClient


def _client() -> CcxtExchangeClient:
    client = CcxtExchangeClient(
        "bitget", default_type="swap", default_sub_type="linear"
    )
    mock = MagicMock()
    mock.has = {
        "fetchClosedOrders": True,
        "fetchMyTrades": True,
        "fetchPositionsHistory": True,
        "fetchOrder": True,
    }
    client._client = mock
    return client


def test_history_requests_enable_pagination_and_dedupe() -> None:
    client = _client()
    order = {"id": "order-1", "info": {"orderId": "order-1"}}
    trade = {"id": "trade-1", "info": {"tradeId": "trade-1"}}
    client._client.fetch_closed_orders.return_value = [order, dict(order)]
    client._client.fetch_my_trades.return_value = [trade, dict(trade)]

    orders = client.fetch_closed_orders_history(
        since=1, until=2, symbols=["LINK/USDT:USDT"]
    )
    trades = client.fetch_my_trades_history(
        since=1, until=2, symbols=["LINK/USDT:USDT"]
    )

    assert len(orders) == 1
    assert len(trades) == 1
    order_params = client._client.fetch_closed_orders.call_args.args[-1]
    trade_params = client._client.fetch_my_trades.call_args.args[-1]
    assert order_params == {
        "productType": "USDT-FUTURES",
        "paginate": True,
        "until": 2,
    }
    assert trade_params == order_params


def test_fetch_order_keeps_product_type_param() -> None:
    client = _client()
    client._client.fetch_order.return_value = {"id": "order-1"}

    client.fetch_order("order-1", symbol="LINK/USDT:USDT")

    assert client._client.fetch_order.call_args.args[-1] == {
        "productType": "USDT-FUTURES"
    }
