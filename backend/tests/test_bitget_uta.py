"""Synthetic Bitget UTA contracts, activation and atomic synchronization."""

from copy import deepcopy
import json

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.api import routes_accounts
from app.core.security import encrypt_secret
from app.db.models import (
    Account, AccountType, AccountBalanceCurrent, Exchange,
    ExchangeConnectionState, PositionCurrent, PositionSide,
)
from app.schemas.account import AccountCreate, AccountUpdate
from app.services import sync_service
from app.services.exchange import ccxt_client, factory
from app.services.exchange.ccxt_client import CcxtExchangeClient, _build_exchange


class UtaApi:
    """Fixture API; private responses contain synthetic values only."""

    has = {"fetchTickers": True}

    def __init__(self):
        self.calls = []
        self.info = {"userId": "1234567890", "permType": "read-only", "permissions": ["uta_mgt", "uta_trade"]}
        self.settings = {"uid": "1234567890", "accountMode": "unified", "accountLevel": "advanced", "holdMode": "hedge_mode"}
        self.assets = {
            "usdtEquity": "15102", "accountEquity": "15100",
            "assets": [
                {"coin": "USDT", "equity": "100", "balance": "100", "available": "90", "locked": "10", "debt": "0", "usdValue": "100"},
                {"coin": "BTC", "equity": "0.3", "balance": "0.2", "available": "0.25", "locked": "0", "debt": "0", "usdValue": "15000"},
            ],
        }
        self.positions = {
            "USDT-FUTURES": [{"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 1, "entryPrice": 49000, "markPrice": 50000, "unrealizedPnl": 1000}],
            "COIN-FUTURES": [{"symbol": "ETH/USD:ETH", "side": "short", "contracts": 2, "entryPrice": 2100, "markPrice": 2000, "unrealizedPnl": 0.01}],
            "USDC-FUTURES": [],
        }

    def _response(self, method, data):
        self.calls.append(method)
        return {"code": "00000", "data": deepcopy(data)}

    def privateUtaGetV3AccountInfo(self, params):
        return self._response("info", self.info)

    def privateSpotGetV2SpotAccountInfo(self, params):
        return self._response("classic_info", self.info)

    def privateUtaGetV3AccountSettings(self, params):
        return self._response("settings", self.settings)

    def privateUtaGetV3AccountAssets(self, params):
        assert "productType" not in params
        return self._response("assets", self.assets)

    def fetch_positions(self, *, params):
        assert params["uta"] is True and "productType" not in params
        category = params["category"]
        self.calls.append(category)
        rows = self.positions[category]
        if isinstance(rows, Exception):
            raise rows
        return deepcopy(rows)

    def fetch_tickers(self, symbols, params):
        return {symbol: {"last": 50000} for symbol in symbols}


@pytest.fixture
def uta_client(monkeypatch):
    api = UtaApi()
    monkeypatch.setattr(ccxt_client, "_build_exchange", lambda *_, **__: api)
    return CcxtExchangeClient("bitget", uta=True), api


def make_account(session, *, account_type=AccountType.BITGET_UTA, enabled=True, uid=None):
    exchange = session.exec(select(Exchange).where(Exchange.name == "bitget")).first()
    if exchange is None:
        exchange = Exchange(name="bitget")
        session.add(exchange)
        session.flush()
    account = Account(
        exchange_id=exchange.id, account_name="fixture", account_type=account_type,
        enabled=enabled, api_key_enc=encrypt_secret("synthetic-key"),
        api_secret_enc=encrypt_secret("synthetic-secret"), passphrase_enc=encrypt_secret("synthetic-pass"),
    )
    session.add(account)
    session.flush()
    if uid:
        session.add(ExchangeConnectionState(
            account_id=account.id, status="connected",
            details_json=json.dumps({"uid": uid, "blockers": [], "account_level": "advanced"}),
        ))
    session.commit()
    return account


@pytest.mark.parametrize("uta", [False, True])
def test_ccxt_bitget_route_is_explicit(uta):
    client = _build_exchange("bitget", api_key=None, api_secret=None, passphrase=None, default_type=None, uta=uta)
    assert client.options["uta"] is uta


def test_factory_selects_uta_only_for_bitget(in_memory_session, monkeypatch):
    account = make_account(in_memory_session)
    options = {}
    monkeypatch.setattr(factory, "CcxtExchangeClient", lambda **kwargs: options.update(kwargs))
    factory.build_client_for_account(in_memory_session, account, product_scope=AccountType.COIN_PERP)
    assert options["uta"] is True
    assert options["history_product_type"] == "COIN-FUTURES"
    account.account_type = AccountType.SPOT
    factory.build_client_for_account(in_memory_session, account)
    assert options["uta"] is False


def test_uta_assets_keep_wallet_quantity_and_top_level_equity(uta_client):
    client, api = uta_client
    fetched = client.fetch_all()
    assert fetched.total_equity_usdt == 15102
    btc = fetched.balances[1]
    assert btc.wallet_balance == 0.2 and btc.equity == 0.3
    assert api.calls.count("assets") == 1
    assert {position.product_type for position in fetched.positions} == {"USDT-FUTURES", "COIN-FUTURES"}
    assert "classic_info" not in api.calls


@pytest.mark.parametrize("field,value,expected", [
    ("accountLevel", "basic", "Advanced"),
    ("accountMode", "upgrading", "stable"),
    ("holdMode", "unsupported", "holding"),
    ("uid", "999", "UID differs"),
])
def test_uta_preflight_rejects_unsupported_settings(uta_client, field, value, expected):
    client, api = uta_client
    api.settings[field] = value
    assert any(expected in blocker for blocker in client.fetch_account_details()["blockers"])


@pytest.mark.parametrize("failure", ["write", "missing_permission", "withdraw", "debt", "usdc"])
def test_uta_preflight_blocks_unsupported_permissions_and_exposure(uta_client, failure):
    client, api = uta_client
    if failure == "write":
        api.info["permType"] = "read-and-write"
    elif failure == "missing_permission":
        api.info["permissions"] = ["uta_mgt"]
    elif failure == "withdraw":
        api.info["permissions"].append("withdraw")
    elif failure == "debt":
        api.assets["assets"][0]["debt"] = "1"
    else:
        api.positions["USDC-FUTURES"] = deepcopy(api.positions["USDT-FUTURES"])
    assert client.fetch_account_details()["blockers"]


@pytest.mark.parametrize("mode", ["unified", "hybrid"])
def test_uta_preflight_accepts_stable_advanced_modes(uta_client, mode):
    client, api = uta_client
    api.settings["accountMode"] = mode
    assert client.fetch_account_details()["blockers"] == []


def test_uta_sync_combines_spot_and_both_derivative_categories(in_memory_session, monkeypatch, uta_client):
    account = make_account(in_memory_session)
    client, api = uta_client
    api.positions["USDT-FUTURES"].append({**api.positions["USDT-FUTURES"][0], "side": "short"})
    monkeypatch.setattr(sync_service, "build_client_for_account", lambda *_: client)
    outcome = sync_service.sync_account(in_memory_session, account)
    in_memory_session.commit()
    assert outcome.success
    rows = {(p.canonical_symbol, p.side): p for p in in_memory_session.exec(select(PositionCurrent)).all()}
    assert rows[("BTC-USDT-SPOT", PositionSide.LONG)].qty == 0.2
    assert rows[("BTC-USDT-PERP", PositionSide.LONG)].unrealized_pnl == 1000
    assert rows[("ETH-USD-PERP", PositionSide.SHORT)].unrealized_pnl == 20
    assert ("BTC-USDT-PERP", PositionSide.SHORT) in rows
    assert account.current_equity_usdt == 15102


@pytest.mark.parametrize("failure", ["linear", "inverse", "assets", "persist"])
def test_uta_sync_rolls_back_all_current_data(in_memory_session, monkeypatch, uta_client, failure):
    account = make_account(in_memory_session)
    account.current_equity_usdt = 42
    balance = AccountBalanceCurrent(account_id=account.id, asset="USDT", equity=42)
    position = PositionCurrent(account_id=account.id, canonical_symbol="BTC-USDT-PERP", side=PositionSide.LONG, qty=3)
    in_memory_session.add_all([account, balance, position])
    in_memory_session.commit()
    position_id = position.id
    client, api = uta_client
    if failure in {"linear", "inverse"}:
        api.positions["USDT-FUTURES" if failure == "linear" else "COIN-FUTURES"] = RuntimeError("private data must not leak")
    elif failure == "assets":
        api.assets["usdtEquity"] = "nan"
    else:
        def fail(*_, **__):
            raise RuntimeError("persistence failure")
        monkeypatch.setattr(sync_service, "refresh_account_positions_from_orders", fail)
    monkeypatch.setattr(sync_service, "build_client_for_account", lambda *_: client)
    outcome = sync_service.sync_account(in_memory_session, account)
    in_memory_session.commit()
    assert not outcome.success
    assert in_memory_session.get(PositionCurrent, position_id).qty == 3
    assert in_memory_session.exec(select(AccountBalanceCurrent)).one().equity == 42
    assert in_memory_session.get(Account, account.id).current_equity_usdt == 42
    assert "private data" not in outcome.message


def test_new_uta_is_disabled_and_cannot_enable_without_test(in_memory_session):
    existing = make_account(in_memory_session, enabled=False)
    account = routes_accounts.create_account(AccountCreate(
        exchange_id=existing.exchange_id, account_name="new", account_type=AccountType.BITGET_UTA,
        api_key="key", api_secret="secret", enabled=True,
    ), in_memory_session)
    assert not account.enabled
    with pytest.raises(HTTPException) as caught:
        routes_accounts.update_account(account.id, AccountUpdate(enabled=True), in_memory_session)
    assert caught.value.status_code == 409
    assert not in_memory_session.get(Account, account.id).enabled


def test_uid_exclusivity_and_credential_invalidation(in_memory_session):
    classic = make_account(in_memory_session, account_type=AccountType.SPOT, uid="1234567890")
    uta = make_account(in_memory_session, enabled=False, uid="1234567890")
    with pytest.raises(HTTPException) as caught:
        routes_accounts.update_account(uta.id, AccountUpdate(enabled=True), in_memory_session)
    assert caught.value.status_code == 409
    routes_accounts.update_account(classic.id, AccountUpdate(enabled=False), in_memory_session)
    assert routes_accounts.update_account(uta.id, AccountUpdate(enabled=True), in_memory_session).enabled
    result = routes_accounts.update_account(uta.id, AccountUpdate(api_key="replacement", enabled=True), in_memory_session)
    assert not result.enabled and result.current_equity_usdt is None
    assert in_memory_session.exec(select(ExchangeConnectionState).where(ExchangeConnectionState.account_id == uta.id)).first() is None


def test_uta_mode_change_requires_explicit_migration(in_memory_session):
    account = make_account(in_memory_session)
    with pytest.raises(HTTPException) as caught:
        routes_accounts.update_account(account.id, AccountUpdate(account_type=AccountType.SPOT), in_memory_session)
    assert caught.value.status_code == 409


def test_connection_api_masks_uid_and_never_returns_private_amounts(in_memory_session, monkeypatch, uta_client):
    account = make_account(in_memory_session, enabled=False)
    client, _ = uta_client
    monkeypatch.setattr(routes_accounts, "build_client_for_account", lambda *_: client)
    result = routes_accounts.test_exchange_connection(account.id, in_memory_session)
    assert result.status == "connected"
    assert result.details["uid_masked"] == "***7890"
    serialized = result.model_dump_json()
    assert "1234567890" not in serialized and "15102" not in serialized
    assert "synthetic-secret" not in serialized


def test_non_bitget_cannot_create_uta(in_memory_session):
    exchange = Exchange(name="bybit")
    in_memory_session.add(exchange)
    in_memory_session.commit()
    with pytest.raises(HTTPException) as caught:
        routes_accounts.create_account(AccountCreate(
            exchange_id=exchange.id, account_name="invalid", account_type=AccountType.BITGET_UTA,
            api_key="key", api_secret="secret",
        ), in_memory_session)
    assert caught.value.status_code == 400
