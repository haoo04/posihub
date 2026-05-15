"""Tests for user-specified (non-FIFO) close matching."""

from __future__ import annotations

import pytest
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
from app.services.position_order_close import FifoCloseError, specified_close_position


def _bootstrap_position(
    session: Session,
    *,
    side: PositionSide = PositionSide.LONG,
    qty: float = 1.5,
    mark_price: float = 51000.0,
) -> PositionCurrent:
    exchange = Exchange(name="test-exch-sp")
    session.add(exchange)
    session.flush()

    account = Account(
        exchange_id=exchange.id,
        account_name="test-acct-sp",
        account_type=AccountType.SIMULATED,
        is_simulated=True,
    )
    session.add(account)
    session.flush()

    position = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USDT-PERP",
        side=side,
        qty=qty,
        entry_price=50000.0,
        mark_price=mark_price,
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
    entry_price: float,
) -> PositionOrder:
    order = PositionOrder(
        position_id=position.id,
        source=DataSource.MANUAL,
        open_qty=open_qty,
        remaining_qty=open_qty,
        entry_price=entry_price,
    )
    session.add(order)
    session.flush()
    return order


def test_specified_reverse_fifo_order(in_memory_session: Session) -> None:
    """Close newest leg first — differs from FIFO (A, B, C time order)."""

    position = _bootstrap_position(in_memory_session, qty=1.5)
    order_a = _add_order(
        in_memory_session, position, open_qty=0.5, entry_price=60000.0
    )
    order_b = _add_order(
        in_memory_session, position, open_qty=0.3, entry_price=61000.0
    )
    order_c = _add_order(
        in_memory_session, position, open_qty=0.7, entry_price=62000.0
    )

    result = specified_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=1.0,
        close_price=63000.0,
        legs=[
            (order_c.id, 0.7),
            (order_b.id, 0.3),
        ],
    )

    for o in (order_a, order_b, order_c):
        in_memory_session.refresh(o)
    in_memory_session.refresh(position)

    assert order_a.remaining_qty == pytest.approx(0.5)
    assert order_a.status == PositionOrderStatus.OPEN
    assert order_b.status == PositionOrderStatus.CLOSED
    assert order_c.status == PositionOrderStatus.CLOSED
    assert position.qty == pytest.approx(0.5)

    matched = [(m.open_order_id, m.matched_qty) for m in result.matches]
    assert matched == [
        (order_c.id, pytest.approx(0.7)),
        (order_b.id, pytest.approx(0.3)),
    ]

    expected_pnl = (63000.0 - 62000.0) * 0.7 + (63000.0 - 61000.0) * 0.3
    assert result.realized_pnl == pytest.approx(expected_pnl)


def test_leg_sum_mismatch_raises(in_memory_session: Session) -> None:
    position = _bootstrap_position(in_memory_session, qty=1.0)
    order = _add_order(
        in_memory_session, position, open_qty=1.0, entry_price=50000.0
    )

    with pytest.raises(FifoCloseError, match="sum of leg quantities"):
        specified_close_position(
            in_memory_session,
            position_id=position.id,
            close_qty=1.0,
            close_price=51000.0,
            legs=[(order.id, 0.5)],
        )


def test_leg_exceeds_remaining_raises(in_memory_session: Session) -> None:
    position = _bootstrap_position(in_memory_session, qty=0.5)
    order = _add_order(
        in_memory_session, position, open_qty=0.5, entry_price=50000.0
    )

    with pytest.raises(FifoCloseError, match="exceeds remaining_qty"):
        specified_close_position(
            in_memory_session,
            position_id=position.id,
            close_qty=0.6,
            close_price=51000.0,
            legs=[(order.id, 0.6)],
        )


def test_duplicate_leg_id_raises(in_memory_session: Session) -> None:
    position = _bootstrap_position(in_memory_session, qty=1.0)
    order = _add_order(
        in_memory_session, position, open_qty=1.0, entry_price=50000.0
    )

    with pytest.raises(FifoCloseError, match="duplicate open_order_id"):
        specified_close_position(
            in_memory_session,
            position_id=position.id,
            close_qty=0.3,
            close_price=51000.0,
            legs=[(order.id, 0.1), (order.id, 0.2)],
        )
