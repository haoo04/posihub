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
