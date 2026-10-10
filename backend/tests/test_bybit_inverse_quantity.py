"""USD boundary quantities with unchanged inverse order storage."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.api.deps import get_session
from app.db.models import (
    Account,
    AccountType,
    DataSource,
    Exchange,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionSide,
    PositionSnapshotDaily,
)
from app.main import create_app
from app.services.aggregate.position_aggregator import PositionInput, aggregate_positions
from app.services.exchange.base import RawPosition
from app.services.normalize.normalizer import normalize_positions, upsert_positions
from app.services.normalize.symbol_mapper import SymbolMapper
from app.services.performance.scope import resolve_performance_scope
from app.services.performance.trades import list_trades
from app.services.pnl_calculator import (
    entry_base_to_quote,
    inverse_pnl_coin,
    linear_unrealized_pnl_usdt,
    quantity_context,
    quote_to_entry_base,
)
from app.services.position_order_close import refresh_account_positions_from_orders
from app.services.sync_service import sync_account


@pytest.fixture
def in_memory_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(in_memory_session):
    app = create_app()

    def override_session():
        yield in_memory_session

    app.dependency_overrides[get_session] = override_session
    # No application lifespan: tests must not start the live exchange scheduler.
    client = TestClient(app)
    yield client
    client.close()


def position(
    session,
    *,
    exchange="bybit",
    account_type=AccountType.COIN_PERP,
    symbol="SOL-USD-PERP",
    side=PositionSide.LONG,
):
    exch = session.exec(select(Exchange).where(Exchange.name == exchange)).first()
    if exch is None:
        exch = Exchange(name=exchange)
        session.add(exch)
        session.flush()
    account = Account(exchange_id=exch.id, account_name="test", account_type=account_type)
    session.add(account)
    session.flush()
    pos = PositionCurrent(
        account_id=account.id,
        canonical_symbol=symbol,
        side=side,
        mark_price=98.44,
        source=DataSource.API,
    )
    session.add(pos)
    session.commit()
    return pos


def open_order(client, pos, qty=65, price=98):
    response = client.post(
        "/api/v1/position-orders",
        json={
            "position_id": pos.id,
            "open_qty": qty,
            "entry_price": price,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "exchange,account_type,symbol,mode",
    [
        ("bybit", AccountType.COIN_PERP, "SOL-USD-PERP", "quote_contract"),
        ("bybit", AccountType.USDT_PERP, "SOL-USDT-PERP", "base"),
        ("bitget", AccountType.COIN_PERP, "SOL-USD-PERP", "base"),
        ("binance", AccountType.COIN_PERP, "SOL-USD-PERP", "base"),
        ("bybit", AccountType.SPOT, "SOL-USD-SPOT", "base"),
        ("bybit", AccountType.SIMULATED, "SOL-USD-PERP", "base"),
    ],
)
def test_quantity_scope(exchange, account_type, symbol, mode):
    context = quantity_context(exchange, account_type, symbol)
    assert context == {
        "quantity_mode": mode,
        "quantity_unit": "USD" if mode == "quote_contract" else "SOL",
    }


@pytest.mark.parametrize("side,sign", [(PositionSide.LONG, 1), (PositionSide.SHORT, -1)])
def test_65_usd_round_trip_and_full_close(client, in_memory_session, side, sign):
    pos = position(in_memory_session, side=side)
    order = open_order(client, pos)
    stored = in_memory_session.get(PositionOrder, order["id"])
    assert stored.open_qty == pytest.approx(65 / 98)
    assert order["open_qty"] == order["remaining_qty"] == 65
    assert order["quantity_unit"] == "USD"
    assert inverse_pnl_coin(side, 65, 98, 98.44) == pytest.approx(sign * 0.002964615349)
    assert linear_unrealized_pnl_usdt(side, 98, 98.44, 65 / 98) == pytest.approx(
        sign * 0.291836734694
    )

    response = client.post(
        f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 65, "close_price": 98.44}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["execution"]["close_qty"] == 65
    assert result["matches"][0]["matched_qty"] == 65
    assert result["matches"][0]["quantity_mode"] == "quote_contract"
    assert result["affected_orders"][0]["remaining_qty"] == 0
    assert result["realized_pnl"] == pytest.approx(sign * 0.291836734694)
    assert stored.remaining_qty == pos.qty == 0
    assert in_memory_session.get(
        PositionCloseExecution, result["execution"]["id"]
    ).close_qty == pytest.approx(65 / 98)

    for mark in (80, 500):
        pos.mark_price = mark
        in_memory_session.commit()
        details = client.get(f"/api/v1/position-orders/{order['id']}").json()
        assert details["realized_pnl_native"] == pytest.approx(sign * 0.002964615349)
    assert client.get(f"/api/v1/positions/{pos.id}/close-executions").json()[0]["close_qty"] == 65
    assert client.get(f"/api/v1/positions/{pos.id}/matches").json()[0]["matched_qty"] == 65
    assert client.get("/api/v1/positions?view=split").json()[0]["qty"] == 0


def test_fifo_across_entry_prices_and_harmonic_average(client, in_memory_session):
    pos = position(in_memory_session)
    first = open_order(client, pos, 65, 98)
    second = open_order(client, pos, 35, 105)
    assert pos.entry_price == pytest.approx(100 / (65 / 98 + 35 / 105))
    split = client.get("/api/v1/positions?view=split").json()[0]
    assert split["qty"] == split["notional"] == 100
    response = client.post(
        f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 80, "close_price": 100}
    )
    assert response.status_code == 201
    result = response.json()
    assert [m["matched_qty"] for m in result["matches"]] == [65, 15]
    assert in_memory_session.get(PositionOrder, first["id"]).remaining_qty == 0
    assert in_memory_session.get(PositionOrder, second["id"]).remaining_qty == pytest.approx(
        20 / 105
    )
    assert result["execution"]["close_qty"] == 80
    assert pos.entry_price == pytest.approx(105)


def test_partial_close_and_price_edits_preserve_usd(client, in_memory_session):
    pos = position(in_memory_session)
    order = open_order(client, pos)
    assert (
        client.post(
            f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 30, "close_price": 98.44}
        ).status_code
        == 201
    )
    response = client.patch(f"/api/v1/position-orders/{order['id']}", json={"entry_price": 120})
    assert response.status_code == 200
    assert response.json()["open_qty"] == 65
    assert response.json()["remaining_qty"] == 35
    stored = in_memory_session.get(PositionOrder, order["id"])
    assert stored.open_qty == pytest.approx(65 / 120)
    assert stored.remaining_qty == pytest.approx(35 / 120)
    response = client.patch(
        f"/api/v1/position-orders/{order['id']}",
        json={"entry_price": 150, "open_qty": 70, "remaining_qty": 40},
    )
    assert response.json()["remaining_qty"] == 40
    assert stored.open_qty == pytest.approx(70 / 150)


@pytest.mark.parametrize("close_method", ["close-fifo", "close-specified"])
def test_legacy_quantity_no_drift_and_tolerance(client, in_memory_session, close_method):
    pos = position(in_memory_session)
    stored = PositionOrder(
        position_id=pos.id, open_qty=0.6632653, remaining_qty=0.6632653, entry_price=98
    )
    in_memory_session.add(stored)
    in_memory_session.commit()
    response = client.get(f"/api/v1/position-orders/{stored.id}")
    assert response.json()["open_qty"] == 65
    assert client.get(f"/api/v1/position-orders?position_id={pos.id}").json()[0]["open_qty"] == 65
    response = client.patch(
        f"/api/v1/position-orders/{stored.id}",
        json={"open_qty": 65, "remaining_qty": 65, "entry_price": 98},
    )
    assert response.status_code == 200
    assert stored.open_qty == stored.remaining_qty == 0.6632653
    payload = {"close_qty": 65.00001, "close_price": 98.44}
    if close_method == "close-specified":
        payload["legs"] = [{"open_order_id": stored.id, "qty": 65.00001}]
    assert (
        client.post(f"/api/v1/positions/{pos.id}/{close_method}", json=payload).status_code == 400
    )
    other = open_order(client, pos, 35, 105)
    payload["close_qty"] = 65
    if "legs" in payload:
        payload["legs"][0]["qty"] = 65
    response = client.post(f"/api/v1/positions/{pos.id}/{close_method}", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["execution"]["close_qty"] == 65
    assert stored.remaining_qty == 0
    assert len(response.json()["matches"]) == 1
    assert in_memory_session.get(PositionOrder, other["id"]).remaining_qty == pytest.approx(35 / 105)


def test_specified_leg_validation_and_native_pnl_sum(client, in_memory_session):
    pos = position(in_memory_session)
    first = open_order(client, pos, 65, 98)
    second = open_order(client, pos, 35, 105)
    payload = {
        "close_qty": 30,
        "close_price": 100,
        "legs": [
            {"open_order_id": second["id"], "qty": 20},
            {"open_order_id": first["id"], "qty": 20},
        ],
    }
    assert (
        client.post(f"/api/v1/positions/{pos.id}/close-specified", json=payload).status_code == 400
    )
    assert not in_memory_session.exec(select(PositionCloseExecution)).all()
    payload["close_qty"] = 40
    response = client.post(f"/api/v1/positions/{pos.id}/close-specified", json=payload)
    assert response.status_code == 201
    assert [m["matched_qty"] for m in response.json()["matches"]] == [20, 20]
    client.post(
        f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 10, "close_price": 110}
    )
    expected_native = inverse_pnl_coin(PositionSide.LONG, 20, 98, 100) + inverse_pnl_coin(
        PositionSide.LONG, 10, 98, 110
    )
    details = client.get(f"/api/v1/position-orders/{first['id']}").json()
    assert details["realized_pnl_native"] == pytest.approx(expected_native)
    assert in_memory_session.get(PositionOrder, second["id"]).remaining_qty == pytest.approx(
        15 / 105
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"open_qty": -1, "entry_price": 98},
        {"open_qty": 65, "entry_price": 0},
        {"open_qty": 65, "entry_price": 98, "quantity_mode": "base"},
    ],
)
def test_invalid_order_requests(client, in_memory_session, payload):
    pos = position(in_memory_session)
    response = client.post("/api/v1/position-orders", json={"position_id": pos.id, **payload})
    assert response.status_code == 422
    assert not in_memory_session.exec(select(PositionOrder)).all()


def test_invalid_quantity_context(client, in_memory_session):
    pos = position(in_memory_session, symbol="SOL-USDT-PERP")
    assert (
        client.post(
            "/api/v1/position-orders",
            json={"position_id": pos.id, "open_qty": 65, "entry_price": 98},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 65, "close_price": 98.44}
        ).status_code
        == 400
    )


def test_fractional_usd_is_not_rounded(client, in_memory_session):
    pos = position(in_memory_session)
    order = open_order(client, pos, 65.25)
    assert order["open_qty"] == pytest.approx(65.25)
    result = client.post(
        f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 0.125, "close_price": 100}
    ).json()
    assert result["execution"]["close_qty"] == pytest.approx(0.125)
    assert result["affected_orders"][0]["remaining_qty"] == pytest.approx(65.125)
    assert quote_to_entry_base(65, 98) == pytest.approx(0.663265306122)
    assert entry_base_to_quote(0.6632653, 98) == 65


def test_multi_order_legacy_full_close_combines_usd_tolerances(client, in_memory_session):
    pos = position(in_memory_session)
    for qty, price in [(0.66326531, 98), (0.33333334, 105)]:
        in_memory_session.add(PositionOrder(position_id=pos.id, open_qty=qty, remaining_qty=qty, entry_price=price))
    in_memory_session.commit()
    response = client.post(f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 100, "close_price": 110})
    assert response.status_code == 201
    assert response.json()["execution"]["close_qty"] == 100
    assert all(order["remaining_qty"] == 0 for order in response.json()["affected_orders"])
    assert pos.qty == 0


def test_small_positive_decimal_quantity_survives_conversion(client, in_memory_session):
    pos = position(in_memory_session)
    order = open_order(client, pos, 0.00000001)
    assert order["open_qty"] == pytest.approx(0.00000001, abs=1e-15)
    assert pos.qty > 0


def test_fifo_exhausted_legacy_leg_has_no_float_tail(client, in_memory_session):
    pos = position(in_memory_session)
    first = PositionOrder(position_id=pos.id, open_qty=0.33333334, remaining_qty=0.33333334, entry_price=98)
    second = PositionOrder(position_id=pos.id, open_qty=1, remaining_qty=1, entry_price=100)
    in_memory_session.add_all([first, second])
    in_memory_session.commit()
    response = client.post(f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 50, "close_price": 110})
    assert response.status_code == 201
    assert first.remaining_qty == 0
    assert second.remaining_qty > 0
    assert response.json()["execution"]["close_qty"] == 50


def test_sync_contract_size_and_invalid_entry_preserve_last_position(
    client, in_memory_session, monkeypatch
):
    pos = position(in_memory_session)
    open_order(client, pos)
    raw = RawPosition("SOL/USD:SOL", "long", 32.5, 98, 98.44, 0.002964615349, contract_size=2)
    normalized = normalize_positions(
        account_id=pos.account_id,
        exchange_name="bybit",
        account_type=AccountType.COIN_PERP,
        raws=[raw],
        mapper=SymbolMapper(in_memory_session),
    )
    assert normalized[0].qty == pytest.approx(65 / 98)
    assert normalized[0].unrealized_pnl == pytest.approx(0.291836734694)
    upsert_positions(in_memory_session, pos.account_id, normalized)
    in_memory_session.flush()
    refresh_account_positions_from_orders(in_memory_session, pos.account_id)
    assert pos.qty == pytest.approx(65 / 98)
    raw.entry_price = 0
    monkeypatch.setattr(
        "app.services.sync_service.build_client_for_account",
        lambda *_: SimpleNamespace(
            fetch_balance=lambda: [], fetch_positions=lambda: [raw], close=lambda: None
        ),
    )
    outcome = sync_account(in_memory_session, in_memory_session.get(Account, pos.account_id))
    assert not outcome.success
    assert "positive entry_price" in outcome.message
    assert pos.qty == pytest.approx(65 / 98)


def test_merged_quantities_do_not_mix_and_net_usd(client, in_memory_session):
    long = position(in_memory_session)
    short = position(in_memory_session, side=PositionSide.SHORT)
    other = position(in_memory_session, exchange="bitget")
    other.qty = 1
    other.entry_price = 100
    in_memory_session.commit()
    open_order(client, long, 65, 98)
    open_order(client, short, 65, 105)
    open_order(client, other, 1, 100)
    merged = client.get("/api/v1/positions?view=merged").json()
    assert len(merged) == 1
    assert merged[0]["quantity_mode"] == "base"
    open_order(client, short, 35, 110)
    merged = client.get("/api/v1/positions?view=merged").json()
    quote = next(row for row in merged if row["quantity_mode"] == "quote_contract")
    assert quote["qty"] == 35
    assert quote["side"] == "short"
    assert quote["notional"] == -35
    assert quote["avg_entry_price"] == pytest.approx(100 / (65 / 105 + 35 / 110))


def test_aggregate_harmonic_average():
    inputs = [
        PositionInput(
            account_id=i,
            canonical_symbol="SOL-USD-PERP",
            side=PositionSide.LONG,
            qty=q / e,
            entry_price=e,
            mark_price=100,
            quantity_mode="quote_contract",
            quantity_unit="USD",
        )
        for i, q, e in [(1, 65, 98), (2, 35, 105)]
    ]
    merged = aggregate_positions(inputs)[0]
    assert merged.qty == merged.notional == 100
    assert merged.avg_entry_price == pytest.approx(100 / (65 / 98 + 35 / 105))


def test_manual_snapshot_storage_and_account_type_guard(client, in_memory_session):
    pos = position(in_memory_session)
    response = client.post(
        "/api/v1/manual/snapshot",
        json={
            "account_id": pos.account_id,
            "snapshot_date": "2026-10-10",
            "positions": [
                {
                    "canonical_symbol": "SOL-USD-PERP",
                    "side": "long",
                    "qty": 65,
                    "entry_price": 98,
                    "mark_price": 98.44,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    stored = in_memory_session.exec(select(PositionSnapshotDaily)).one()
    assert stored.qty == pytest.approx(65 / 98)
    snapshot = client.get("/api/v1/snapshots/daily/positions").json()[0]
    assert snapshot["qty"] == 65
    assert snapshot["quantity_unit"] == "USD"
    assert (
        client.patch(
            f"/api/v1/accounts/{pos.account_id}", json={"account_type": "usdt_perp"}
        ).status_code
        == 400
    )


def test_order_history_blocks_account_type_change(client, in_memory_session):
    pos = position(in_memory_session)
    assert (
        client.patch(
            f"/api/v1/accounts/{pos.account_id}", json={"account_type": "coin_perp"}
        ).status_code
        == 200
    )
    open_order(client, pos)
    assert (
        client.patch(
            f"/api/v1/accounts/{pos.account_id}", json={"account_type": "spot"}
        ).status_code
        == 400
    )


def test_performance_external_quantity_sort_hold_weight_and_missing_matches(
    client, in_memory_session
):
    pos = position(in_memory_session)
    first = open_order(client, pos, 30, 50)
    second = open_order(client, pos, 70, 200)
    for order_id, hours in [(first["id"], 10), (second["id"], 2)]:
        in_memory_session.get(PositionOrder, order_id).created_at = datetime(
            2026, 10, 10, 12
        ) - timedelta(hours=hours)
    result = client.post(
        f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 100, "close_price": 100}
    ).json()
    execution = in_memory_session.get(PositionCloseExecution, result["execution"]["id"])
    execution.created_at = datetime(2026, 10, 10, 12)
    open_order(client, pos, 50, 10)
    second_result = client.post(
        f"/api/v1/positions/{pos.id}/close-fifo", json={"close_qty": 50, "close_price": 100}
    ).json()
    in_memory_session.get(PositionCloseExecution, second_result["execution"]["id"]).created_at = (
        datetime(2026, 10, 10, 12)
    )
    missing = PositionCloseExecution(
        position_id=pos.id, close_qty=1, close_price=100, created_at=datetime(2026, 10, 10, 12)
    )
    in_memory_session.add(missing)
    in_memory_session.commit()
    scope = resolve_performance_scope(in_memory_session)
    rows = list_trades(
        in_memory_session,
        scope=scope,
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 10),
        sort_field="close_qty",
        sort_desc=True,
    ).items
    assert [row.close_qty for row in rows] == [100, 50, None]
    assert rows[0].hold_duration_hours == pytest.approx(4.4)
    assert rows[0].quantity_unit == "USD"
    assert rows[2].quantity_warning
    assert (
        next(
            row
            for row in client.get(f"/api/v1/positions/{pos.id}/close-executions").json()
            if row["id"] == missing.id
        )["close_qty"]
        is None
    )
