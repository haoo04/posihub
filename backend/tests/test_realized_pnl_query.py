"""Tests for realized PnL aggregation helpers and list endpoints."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.models import (
    Account,
    AccountType,
    DataSource,
    Exchange,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
)
from app.services.position_order_close import fifo_close_position
from app.services.realized_pnl_query import (
    close_price_by_open_order_id,
    realized_pnl_totals_by_open_order_id,
    realized_pnl_totals_by_position_id,
)


def _bootstrap_long_position(session: Session) -> tuple[PositionCurrent, PositionOrder]:
    exchange = Exchange(name="test-exch-rp")
    session.add(exchange)
    session.flush()

    account = Account(
        exchange_id=exchange.id,
        account_name="acct-rp",
        account_type=AccountType.SIMULATED,
        is_simulated=True,
    )
    session.add(account)
    session.flush()

    position = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USDT-PERP",
        side=PositionSide.LONG,
        qty=1.0,
        entry_price=50_000.0,
        mark_price=52_000.0,
        unrealized_pnl=0.0,
        source=DataSource.MANUAL,
    )
    session.add(position)
    session.flush()

    order = PositionOrder(
        position_id=position.id,
        source=DataSource.MANUAL,
        open_qty=1.0,
        remaining_qty=1.0,
        entry_price=50_000.0,
        status=PositionOrderStatus.OPEN,
    )
    session.add(order)
    session.flush()
    return position, order


def test_totals_by_position_and_order_after_fifo_close(in_memory_session: Session) -> None:
    position, order = _bootstrap_long_position(in_memory_session)
    result = fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.4,
        close_price=52_000.0,
    )
    in_memory_session.commit()

    assert result.realized_pnl == pytest.approx((52_000.0 - 50_000.0) * 0.4)

    by_pos = realized_pnl_totals_by_position_id(in_memory_session)
    assert by_pos[int(position.id)] == pytest.approx(result.realized_pnl)

    by_order = realized_pnl_totals_by_open_order_id(
        in_memory_session, [int(order.id)]
    )
    assert by_order[int(order.id)] == pytest.approx(result.realized_pnl)


@pytest.fixture()
def client_overridden_session(
    in_memory_session: Session,
) -> Iterator[TestClient]:
    from app.api.deps import get_session
    from app.main import create_app

    def override_get_session() -> Iterator[Session]:
        yield in_memory_session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_positions_split_and_order_list_expose_realized_pnl(
    in_memory_session: Session,
    client_overridden_session: TestClient,
) -> None:
    position, order = _bootstrap_long_position(in_memory_session)
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.25,
        close_price=48_000.0,
    )
    in_memory_session.commit()

    pid = int(position.id)
    oid = int(order.id)

    r1 = client_overridden_session.get("/api/v1/positions?view=split")
    assert r1.status_code == 200
    rows = r1.json()
    hit = next(x for x in rows if x["id"] == pid)
    assert hit["realized_pnl"] == pytest.approx((48_000.0 - 50_000.0) * 0.25)

    r2 = client_overridden_session.get(
        f"/api/v1/position-orders/by-position/{pid}"
    )
    assert r2.status_code == 200
    orders = r2.json()
    ohit = next(x for x in orders if x["id"] == oid)
    assert ohit["realized_pnl"] == pytest.approx((48_000.0 - 50_000.0) * 0.25)
    assert ohit["remaining_qty"] == pytest.approx(0.75)
    assert ohit["close_price"] == pytest.approx(48_000.0)


def test_close_price_weighted_average(in_memory_session: Session) -> None:
    position, order = _bootstrap_long_position(in_memory_session)
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.4,
        close_price=52_000.0,
    )
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.6,
        close_price=53_000.0,
    )
    in_memory_session.commit()

    cp = close_price_by_open_order_id(in_memory_session, [int(order.id)])
    expected = (52_000.0 * 0.4 + 53_000.0 * 0.6) / 1.0
    assert cp[int(order.id)] == pytest.approx(expected)


def test_coin_perp_order_pnl_native_fields(
    in_memory_session: Session,
    client_overridden_session: TestClient,
) -> None:
    exchange = Exchange(name="coin-exch")
    in_memory_session.add(exchange)
    in_memory_session.flush()

    account = Account(
        exchange_id=exchange.id,
        account_name="coin-acct",
        account_type=AccountType.COIN_PERP,
        is_simulated=True,
    )
    in_memory_session.add(account)
    in_memory_session.flush()

    position = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USD-PERP",
        side=PositionSide.LONG,
        qty=1.0,
        entry_price=50_000.0,
        mark_price=52_000.0,
        unrealized_pnl=0.0,
        source=DataSource.MANUAL,
    )
    in_memory_session.add(position)
    in_memory_session.flush()

    order = PositionOrder(
        position_id=position.id,
        source=DataSource.MANUAL,
        open_qty=1.0,
        remaining_qty=1.0,
        entry_price=50_000.0,
        status=PositionOrderStatus.OPEN,
    )
    in_memory_session.add(order)
    in_memory_session.commit()

    pid = int(position.id)
    r = client_overridden_session.get(f"/api/v1/position-orders/by-position/{pid}")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["pnl_asset"] == "BTC"
    assert row["unrealized_pnl_usdt"] == pytest.approx(2_000.0)
    assert row["unrealized_pnl_native"] == pytest.approx(2_000.0 / 52_000.0)

    rpos = client_overridden_session.get("/api/v1/positions?view=split")
    phit = next(x for x in rpos.json() if x["id"] == pid)
    assert phit["account_type"] == "coin_perp"
    assert phit["pnl_asset"] == "BTC"


def test_position_matches_list_after_fifo_close(
    in_memory_session: Session,
    client_overridden_session: TestClient,
) -> None:
    position, order = _bootstrap_long_position(in_memory_session)
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.25,
        close_price=48_000.0,
    )
    in_memory_session.commit()

    pid = int(position.id)
    oid = int(order.id)

    r = client_overridden_session.get(f"/api/v1/positions/{pid}/matches")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["open_order_id"] == oid
    assert rows[0]["matched_qty"] == pytest.approx(0.25)
    assert rows[0]["close_price"] == pytest.approx(48_000.0)
    assert rows[0]["realized_pnl"] == pytest.approx((48_000.0 - 50_000.0) * 0.25)
