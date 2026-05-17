"""Tests for Bitget coin-margined (inverse) CCXT workarounds."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.exchange.ccxt_client import (
    CcxtExchangeClient,
    bitget_fetch_params,
)


def test_bitget_fetch_params_inverse() -> None:
    assert bitget_fetch_params("bitget", "inverse") == {"productType": "COIN-FUTURES"}


def test_bitget_fetch_params_linear() -> None:
    assert bitget_fetch_params("bitget", "linear") == {"productType": "USDT-FUTURES"}


def test_bitget_fetch_params_other_exchange() -> None:
    assert bitget_fetch_params("binance", "inverse") == {}


def test_fetch_bitget_coin_positions_uses_margin_coin_not_usdt() -> None:
    client = CcxtExchangeClient(
        "bitget",
        default_type="swap",
        default_sub_type="inverse",
    )
    mock_ccxt = MagicMock()
    mock_ccxt.privateMixGetV2MixAccountAccounts.return_value = {
        "data": [{"marginCoin": "BTC"}, {"marginCoin": "ETH"}],
    }
    mock_ccxt.fetch_balance.return_value = {"total": {}, "free": {}, "used": {}}
    mock_ccxt.fetch_positions.return_value = [
        {
            "symbol": "BTC/USD:BTC",
            "side": "long",
            "contracts": 1.0,
            "entryPrice": 60000.0,
            "markPrice": 61000.0,
            "unrealizedPnl": 10.0,
            "contractSize": 1.0,
        }
    ]
    client._client = mock_ccxt

    positions = client._fetch_bitget_coin_futures_positions()

    assert len(positions) >= 1
    mock_ccxt.fetch_positions.assert_any_call(
        params={"productType": "COIN-FUTURES", "marginCoin": "BTC"}
    )
    mock_ccxt.fetch_positions.assert_any_call(
        params={"productType": "COIN-FUTURES", "marginCoin": "ETH"}
    )


def test_fetch_positions_linear_passes_params_keyword() -> None:
    client = CcxtExchangeClient(
        "bitget",
        default_type="swap",
        default_sub_type="linear",
    )
    mock_ccxt = MagicMock()
    mock_ccxt.fetch_positions.return_value = []
    client._client = mock_ccxt

    client.fetch_positions()

    mock_ccxt.fetch_positions.assert_called_once_with(
        params={"productType": "USDT-FUTURES"}
    )


def test_fetch_positions_routes_bitget_inverse() -> None:
    client = CcxtExchangeClient(
        "bitget",
        default_type="swap",
        default_sub_type="inverse",
    )
    sample = [
        {
            "symbol": "BTC/USD:BTC",
            "side": "long",
            "contracts": 2.0,
            "entryPrice": 1.0,
            "markPrice": 2.0,
            "unrealizedPnl": 0.0,
            "contractSize": 1.0,
        }
    ]
    with patch.object(client, "_fetch_bitget_coin_futures_positions", return_value=sample):
        parsed = client.fetch_positions()
    assert len(parsed) == 1
    assert parsed[0].raw_symbol == "BTC/USD:BTC"
