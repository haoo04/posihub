"""Tests for position-order list ordering."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.api.deps import get_session
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
from app.main import create_app


@pytest.fixture
def in_memory_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client_overridden_session(
    in_memory_session: Session,
) -> Iterator[TestClient]:
    def override_get_session() -> Iterator[Session]:
        yield in_memory_session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _bootstrap_position(session: Session) -> PositionCurrent:
    exchange = Exchange(name="list-exch")
    session.add(exchange)
    session.flush()

    account = Account(
        exchange_id=exchange.id,
        account_name="list-acct",
        account_type=AccountType.SIMULATED,
        is_simulated=True,
    )
    session.add(account)
    session.flush()

    position = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USDT-PERP",
        side=PositionSide.LONG,
        qty=3.0,
        entry_price=50_000.0,
        mark_price=51_000.0,
        source=DataSource.MANUAL,
    )
    session.add(position)
    session.flush()
    return position


def _add_order(
    session: Session,
    position: PositionCurrent,
    *,
    open_qty: float,
    created_offset_seconds: int,
) -> PositionOrder:
    base = datetime.now(timezone.utc).replace(tzinfo=None)
    order = PositionOrder(
        position_id=position.id,
        source=DataSource.MANUAL,
        open_qty=open_qty,
        remaining_qty=open_qty,
        entry_price=50_000.0,
        status=PositionOrderStatus.OPEN,
        created_at=base + timedelta(seconds=created_offset_seconds),
        updated_at=base + timedelta(seconds=created_offset_seconds),
    )
    session.add(order)
    session.flush()
    return order


def test_by_position_orders_sorted_by_created_at_asc(
    in_memory_session: Session,
    client_overridden_session: TestClient,
) -> None:
    position = _bootstrap_position(in_memory_session)
    third = _add_order(
        in_memory_session, position, open_qty=0.3, created_offset_seconds=30
    )
    first = _add_order(
        in_memory_session, position, open_qty=0.1, created_offset_seconds=0
    )
    second = _add_order(
        in_memory_session, position, open_qty=0.2, created_offset_seconds=10
    )
    in_memory_session.commit()

    pid = int(position.id)
    r = client_overridden_session.get(f"/api/v1/position-orders/by-position/{pid}")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [int(first.id), int(second.id), int(third.id)]


def test_list_position_orders_with_position_id_filter_sorted(
    in_memory_session: Session,
    client_overridden_session: TestClient,
) -> None:
    position = _bootstrap_position(in_memory_session)
    late = _add_order(
        in_memory_session, position, open_qty=0.5, created_offset_seconds=20
    )
    early = _add_order(
        in_memory_session, position, open_qty=0.5, created_offset_seconds=0
    )
    in_memory_session.commit()

    pid = int(position.id)
    r = client_overridden_session.get(
        "/api/v1/position-orders", params={"position_id": pid}
    )
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [int(early.id), int(late.id)]
