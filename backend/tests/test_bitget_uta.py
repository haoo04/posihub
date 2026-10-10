"""Synthetic Bitget UTA contracts, activation and atomic synchronization."""

from copy import deepcopy
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.api import routes_accounts
from app.api import routes_history_import, routes_overview
from app.core.security import encrypt_secret
from app.db.models import (
    Account, AccountType, AccountBalanceCurrent, Exchange,
    ExchangeConnectionState, PositionCurrent, PositionSide,
    AccountSnapshotDaily, DataMigration, HistoryImportPreview, PositionOrder,
)
from app.schemas.account import AccountCreate, AccountUpdate
from app.services import sync_service
from app.services import snapshot_service
from app.services.exchange import ccxt_client, factory
from app.services.exchange.ccxt_client import CcxtExchangeClient, _build_exchange
from app.schemas.history_import import HistoryImportPreviewRequest, HistoryImportCommitRequest
from app.services.history_import.normalize_bitget import aggregate_bitget_trades_to_order_raw, normalize_bitget_order
from app.services.performance.equity_metrics import compute_equity_metrics
from app.services.performance.scope import PerformanceScope


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

    def load_markets(self):
        return {}

    def safe_market(self, symbol, *_):
        return {"symbol": "BTC/USD:BTC" if symbol.startswith("BTCUSD") and not symbol.startswith("BTCUSDT") else "BTC/USDT:USDT"}


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
        original = sync_service.upsert_positions
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("persistence failure")
        monkeypatch.setattr(sync_service, "upsert_positions", fail)
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
    state = in_memory_session.exec(select(ExchangeConnectionState).where(ExchangeConnectionState.account_id == uta.id)).one()
    assert state.status == "unknown" and json.loads(state.details_json) == {"owner_uid": "1234567890"}


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


def test_overview_counts_uta_equity_once_and_excludes_disabled_accounts(in_memory_session):
    uta = make_account(in_memory_session)
    classic = make_account(in_memory_session, account_type=AccountType.USDT_PERP)
    retired = make_account(in_memory_session, account_type=AccountType.SPOT, enabled=False)
    uta.current_equity_usdt = 150
    in_memory_session.add_all([
        uta,
        AccountBalanceCurrent(account_id=uta.id, asset="USDT", equity=100),
        AccountBalanceCurrent(account_id=uta.id, asset="BTC", equity=2),
        AccountBalanceCurrent(account_id=classic.id, asset="USDT", equity=50),
        AccountBalanceCurrent(account_id=retired.id, asset="USDT", equity=999),
        PositionCurrent(account_id=retired.id, canonical_symbol="BTC-USDT-SPOT", qty=10),
    ])
    in_memory_session.commit()
    result = routes_overview.get_overview(in_memory_session)
    assert result.total_equity == 200 and result.total_accounts == 2
    assert result.total_positions == 0


def test_daily_uta_snapshot_is_unique_and_keeps_retired_history(in_memory_session, monkeypatch):
    uta = make_account(in_memory_session)
    retired = make_account(in_memory_session, account_type=AccountType.SPOT, enabled=False)
    today = date.today()
    uta.current_equity_usdt = 150
    uta.created_at = datetime(2020, 1, 1)
    original = AccountSnapshotDaily(account_id=retired.id, snapshot_date=today, asset="USDT", total_equity=40)
    in_memory_session.add_all([
        uta, original,
        AccountBalanceCurrent(account_id=uta.id, asset="USDT", equity=100),
        AccountBalanceCurrent(account_id=uta.id, asset="BTC", equity=2),
    ])
    in_memory_session.commit()
    original_id = original.id

    @contextmanager
    def session_scope():
        yield in_memory_session
        in_memory_session.commit()

    monkeypatch.setattr(snapshot_service, "session_scope", session_scope)
    snapshot_service.write_daily_snapshots(today)
    snapshot_service.write_daily_snapshots(today)
    rows = in_memory_session.exec(select(AccountSnapshotDaily).where(AccountSnapshotDaily.account_id == uta.id)).all()
    assert len(rows) == 1 and rows[0].asset == "USDT"
    assert rows[0].total_equity == 150 and rows[0].total_available == 0
    assert in_memory_session.get(AccountSnapshotDaily, original_id).total_equity == 40


def test_uta_performance_excludes_old_basis_and_uses_live_total(in_memory_session):
    uta = make_account(in_memory_session)
    uta.current_equity_usdt = 160
    in_memory_session.add_all([
        uta,
        DataMigration(key=f"bitget-uta-cutover-v1:{uta.id}", details_json=json.dumps({"cutover_date": "2026-10-02"})),
        AccountSnapshotDaily(account_id=uta.id, snapshot_date=date(2026, 10, 1), total_equity=999),
        AccountSnapshotDaily(account_id=uta.id, snapshot_date=date(2026, 10, 2), total_equity=150),
        AccountBalanceCurrent(account_id=uta.id, asset="USDT", equity=20),
    ])
    in_memory_session.commit()
    scope = PerformanceScope([uta.id], None, False)
    result = compute_equity_metrics(in_memory_session, scope=scope, start_date=date(2026, 10, 1), end_date=date(2026, 10, 3))
    assert [point.total_equity for point in result.points] == [150, 160]
    assert result.first_snapshot_date == date(2026, 10, 2)
    earlier = compute_equity_metrics(in_memory_session, scope=scope, start_date=date(2026, 9, 1), end_date=date(2026, 10, 1))
    assert earlier.points == [] and earlier.equity_end == 0


def native_order(order_id, timestamp, *, side="buy", qty="1", category="USDT-FUTURES"):
    return {
        "orderId": order_id, "symbol": "BTCUSDT" if category == "USDT-FUTURES" else "BTCUSD_CM",
        "category": category, "posSide": "long", "side": side, "reduceOnly": "NO",
        "cumExecQty": qty, "avgPrice": "100", "createdTime": str(timestamp),
        "updatedTime": str(timestamp), "orderStatus": "filled", "marginMode": "crossed",
    }


@pytest.mark.parametrize("days", [30, 31, 60, 90])
def test_uta_history_windows_and_boundary_dedup(uta_client, monkeypatch, days):
    client, api = uta_client
    now = 2000000000000
    monkeypatch.setattr(ccxt_client.time, "time", lambda: now / 1000)
    calls = []

    def page(params):
        calls.append(dict(params))
        return {"code": "00000", "data": {"list": [native_order("same", params["startTime"])], "cursor": ""}}

    api.privateUtaGetV3TradeHistoryOrders = page
    rows = client.fetch_closed_orders_history(since=now - days * 86400000, until=now)
    assert len(rows) == 1
    assert len(calls) == (days + 29) // 30
    assert all(call["endTime"] - call["startTime"] <= 30 * 86400000 for call in calls)
    assert all(left["endTime"] + 1 == right["startTime"] for left, right in zip(calls, calls[1:]))
    assert calls[-1]["endTime"] == now


def test_uta_cursor_reads_more_than_ten_pages(uta_client, monkeypatch):
    client, api = uta_client
    now = 2000000000000
    monkeypatch.setattr(ccxt_client.time, "time", lambda: now / 1000)
    client._history_product_type = "COIN-FUTURES"
    calls = []

    def page(params):
        index = int(params.get("cursor", 0))
        assert params["category"] == "COIN-FUTURES" and "symbol" not in params
        calls.append(index)
        return {"code": "00000", "data": {"list": [native_order(str(index), now - 1000, category="COIN-FUTURES")], "cursor": str(index + 1) if index < 11 else ""}}

    api.privateUtaGetV3TradeHistoryOrders = page
    assert len(client.fetch_closed_orders_history(since=now - 86400000, until=now)) == 12
    assert calls == list(range(12))


@pytest.mark.parametrize("days", [91, -1])
def test_uta_history_rejects_unavailable_ranges(uta_client, monkeypatch, days):
    client, _ = uta_client
    now = 2000000000000
    monkeypatch.setattr(ccxt_client.time, "time", lambda: now / 1000)
    with pytest.raises(ValueError, match="90 days"):
        client.fetch_closed_orders_history(since=now - days * 86400000, until=now)


def test_uta_history_requires_product_scope_before_network(in_memory_session, monkeypatch):
    account = make_account(in_memory_session)
    monkeypatch.setattr(routes_history_import, "build_client_for_account", lambda *_: pytest.fail("must not call exchange"))
    now = datetime.now(timezone.utc)
    with pytest.raises(HTTPException) as caught:
        routes_history_import.preview_history_import(account.id, HistoryImportPreviewRequest(since=now - timedelta(days=1), until=now), in_memory_session)
    assert caught.value.status_code == 400 and "product_scope" in caught.value.detail


def configure_history(api, since_ms, *, fail=None):
    orders = [native_order("open", since_ms + 1000), native_order("close", since_ms + 2000, side="sell")]
    trades = [{
        "execId": f"fill-{row['orderId']}", "orderId": row["orderId"], "category": row["category"],
        "symbol": row["symbol"], "posSide": "long", "side": row["side"], "execQty": "1",
        "execPrice": "100", "execTime": row["updatedTime"], "execPnl": "0",
    } for row in orders]

    def orders_page(params):
        if fail == "orders":
            raise RuntimeError("private response should not leak")
        return {"code": "00000", "data": {"list": orders, "cursor": ""}}

    def trades_page(params):
        if fail == "fills":
            raise RuntimeError("private response should not leak")
        return {"code": "00000", "data": {"list": trades, "cursor": ""}}

    def unavailable(params):
        raise RuntimeError("read/write permission required; private UID should not leak")

    api.privateUtaGetV3TradeHistoryOrders = orders_page
    api.privateUtaGetV3TradeFills = trades_page
    api.privateUtaGetV3PositionHistoryPosition = unavailable


@pytest.mark.parametrize("failure", [None, "orders", "fills"])
def test_uta_preview_caches_scope_and_completeness_and_commits_without_network(in_memory_session, monkeypatch, uta_client, failure):
    account = make_account(in_memory_session, uid="1234567890")
    client, api = uta_client
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    since = now - timedelta(days=1)
    configure_history(api, int(since.timestamp() * 1000), fail=failure)

    def build(*_, **kwargs):
        assert kwargs["product_scope"] == AccountType.USDT_PERP
        return client

    monkeypatch.setattr(routes_history_import, "build_client_for_account", build)
    preview = routes_history_import.preview_history_import(account.id, HistoryImportPreviewRequest(since=since, until=now, product_scope="usdt_perp"), in_memory_session)
    data = json.loads(in_memory_session.get(HistoryImportPreview, preview.preview_id).payload_json)
    assert data["product_scope"] == "usdt_perp" and data["complete"] == preview.complete
    monkeypatch.setattr(routes_history_import, "build_client_for_account", lambda *_: pytest.fail("commit must not query exchange"))
    request = HistoryImportCommitRequest(preview_id=preview.preview_id)
    if failure:
        assert not preview.complete and preview.blockers
        with pytest.raises(HTTPException) as caught:
            routes_history_import.commit_history_import_endpoint(account.id, request, in_memory_session)
        assert caught.value.status_code == 400
    else:
        assert preview.complete and not preview.blockers
        assert preview.warnings and "validation_unavailable" in preview.warnings[0]
        assert [order.action for order in preview.orders] == ["open", "close"]
        assert routes_history_import.commit_history_import_endpoint(account.id, request, in_memory_session).created_opens == 1


def test_v3_partially_filled_cancelled_order_and_coin_fill_pnl():
    timestamp = 2000000000000
    raw = native_order("partial", timestamp, qty="0.25")
    raw["orderStatus"] = "cancelled"
    order = normalize_bitget_order({"info": raw, "symbol": "BTC/USDT:USDT"})
    assert order.qty == 0.25 and order.created_at == datetime.fromtimestamp(timestamp / 1000, timezone.utc).replace(tzinfo=None)
    synthesized = aggregate_bitget_trades_to_order_raw("coin-close", [
        {"symbol": "BTC/USD:BTC", "info": {"category": "COIN-FUTURES", "posSide": "long", "side": "sell", "execQty": "1", "execPrice": "200", "execPnl": "0.1", "execTime": timestamp}}
    ])
    closed = normalize_bitget_order(synthesized, fill_time=datetime(2026, 10, 1))
    assert closed.action.value == "close" and closed.realized_pnl == 20


@pytest.mark.parametrize("invalid", ["missing_quantity", "wrong_category", "not_a_list"])
def test_invalid_current_position_response_never_becomes_empty_success(uta_client, invalid):
    client, api = uta_client
    if invalid == "missing_quantity":
        api.positions["COIN-FUTURES"][0].pop("contracts")
    elif invalid == "wrong_category":
        api.positions["COIN-FUTURES"][0]["info"] = {"category": "USDT-FUTURES"}
    else:
        api.positions["COIN-FUTURES"] = None
    with pytest.raises(RuntimeError, match="COIN-FUTURES"):
        client.fetch_all()


def test_uta_sync_keeps_native_quantity_and_pnl_with_partial_local_orders(in_memory_session, monkeypatch, uta_client):
    account = make_account(in_memory_session)
    parent = PositionCurrent(account_id=account.id, canonical_symbol="BTC-USDT-PERP", side=PositionSide.LONG, qty=3)
    in_memory_session.add(parent)
    in_memory_session.flush()
    order = PositionOrder(position_id=parent.id, open_qty=0.5, remaining_qty=0.5, entry_price=100)
    in_memory_session.add(order)
    in_memory_session.commit()
    parent_id = parent.id
    client, api = uta_client
    monkeypatch.setattr(sync_service, "build_client_for_account", lambda *_: client)
    assert sync_service.sync_account(in_memory_session, account).success
    in_memory_session.commit()
    parent = in_memory_session.get(PositionCurrent, parent_id)
    assert parent.qty == 1 and parent.entry_price == 49000 and parent.unrealized_pnl == 1000
    assert order.remaining_qty == 0.5 and order.position_id == parent_id
    api.positions["USDT-FUTURES"] = []
    api.positions["COIN-FUTURES"] = []
    api.assets["assets"][1]["balance"] = "0"
    assert sync_service.sync_account(in_memory_session, account).success
    in_memory_session.commit()
    assert in_memory_session.get(PositionCurrent, parent_id).qty == 0
    assert in_memory_session.get(PositionOrder, order.id).position_id == parent_id


def test_credential_change_invalidates_pending_preview_and_keeps_uid_binding(in_memory_session, monkeypatch, uta_client):
    account = make_account(in_memory_session, enabled=False, uid="1234567890")
    in_memory_session.add(HistoryImportPreview(id="pending", account_id=account.id, expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)))
    in_memory_session.commit()
    routes_accounts.update_account(account.id, AccountUpdate(api_key="replacement"), in_memory_session)
    assert in_memory_session.get(HistoryImportPreview, "pending") is None
    client, api = uta_client
    api.info["userId"] = "9999999999"
    api.settings["uid"] = "9999999999"
    monkeypatch.setattr(routes_accounts, "build_client_for_account", lambda *_: client)
    for _ in range(2):
        result = routes_accounts.test_exchange_connection(account.id, in_memory_session)
        assert result.status == "error" and any("different Bitget UID" in text for text in result.blockers)


def test_uta_performance_includes_verified_zero_live_equity(in_memory_session):
    account = make_account(in_memory_session)
    account.created_at = datetime(2020, 1, 1)
    account.current_equity_usdt = 0
    in_memory_session.add_all([account, AccountSnapshotDaily(account_id=account.id, snapshot_date=date(2026, 10, 1), total_equity=100)])
    in_memory_session.commit()
    result = compute_equity_metrics(in_memory_session, scope=PerformanceScope([account.id], None, False), start_date=date(2026, 10, 1), end_date=date(2026, 10, 2))
    assert [point.total_equity for point in result.points] == [100, 0]
    assert result.equity_end == 0


def test_mixed_uta_tickers_complete_missing_product_categories(uta_client):
    client, api = uta_client
    api.fetch_tickers = lambda symbols, params: {"BTC/USDT:USDT": {"last": 50000}}
    calls = []

    def ticker(symbol, params):
        calls.append(symbol)
        assert params == {"uta": True}
        return {"last": 2000}

    api.fetch_ticker = ticker
    result = client.fetch_last_prices(["BTC/USDT:USDT", "ETH/USD:ETH"])
    assert result == {"BTC/USDT:USDT": 50000, "ETH/USD:ETH": 2000}
    assert calls == ["ETH/USD:ETH"]
