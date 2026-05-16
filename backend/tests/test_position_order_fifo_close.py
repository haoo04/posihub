"""Tests for the FIFO close service (Phase 2).

Covers the scenarios spelled out in
``docs/order-level-position.md`` section 8 (partial close, multi-order
FIFO) plus boundary handling (over-close, non-positive qty) and the
SHORT-side realized PnL sign convention.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.db.models import (
    Account,
    AccountType,
    DataSource,
    Exchange,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionOrderMatch,
    PositionOrderStatus,
    PositionSide,
)
from app.services.position_order_close import (
    FifoCloseError,
    fifo_close_position,
)


def _bootstrap_position(
    session: Session,
    *,
    side: PositionSide = PositionSide.LONG,
    qty: float = 1.0,
    mark_price: float = 51000.0,
) -> PositionCurrent:
    exchange = Exchange(name="test-exch")
    session.add(exchange)
    session.flush()

    account = Account(
        exchange_id=exchange.id,
        account_name="test-acct",
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
    created_offset_seconds: int = 0,
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
    if created_offset_seconds:
        order.created_at = order.created_at + timedelta(
            seconds=created_offset_seconds
        )
        session.add(order)
        session.flush()
    return order


def test_partial_close_single_order_long(in_memory_session: Session) -> None:
    """Doc section 8 - partial close: 1 BTC order, close 0.4."""

    position = _bootstrap_position(in_memory_session, qty=1.0)
    order = _add_order(
        in_memory_session, position, open_qty=1.0, entry_price=50000.0
    )

    result = fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.4,
        close_price=52000.0,
    )

    in_memory_session.refresh(order)
    in_memory_session.refresh(position)

    assert order.remaining_qty == pytest.approx(0.6)
    assert order.status == PositionOrderStatus.PARTIAL
    assert position.qty == pytest.approx(0.6)

    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.matched_qty == pytest.approx(0.4)
    assert match.open_price == pytest.approx(50000.0)
    assert match.close_price == pytest.approx(52000.0)
    assert match.realized_pnl == pytest.approx((52000.0 - 50000.0) * 0.4)
    assert match.open_order_id == order.id
    assert match.close_order_id == result.execution.id

    assert result.execution.close_qty == pytest.approx(0.4)
    assert result.execution.realized_pnl == pytest.approx(800.0)
    assert result.realized_pnl == pytest.approx(800.0)

    assert position.unrealized_pnl == pytest.approx((51000.0 - 50000.0) * 0.6)
    assert position.entry_price == pytest.approx(50000.0)


def test_multi_order_fifo_close_long(in_memory_session: Session) -> None:
    """Doc section 8 - FIFO across A=0.5, B=0.3, C=0.7; close 1.0."""

    position = _bootstrap_position(in_memory_session, qty=1.5)
    order_a = _add_order(
        in_memory_session,
        position,
        open_qty=0.5,
        entry_price=60000.0,
        created_offset_seconds=0,
    )
    order_b = _add_order(
        in_memory_session,
        position,
        open_qty=0.3,
        entry_price=61000.0,
        created_offset_seconds=10,
    )
    order_c = _add_order(
        in_memory_session,
        position,
        open_qty=0.7,
        entry_price=62000.0,
        created_offset_seconds=20,
    )

    result = fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=1.0,
        close_price=63000.0,
    )

    for o in (order_a, order_b, order_c):
        in_memory_session.refresh(o)
    in_memory_session.refresh(position)

    assert order_a.status == PositionOrderStatus.CLOSED
    assert order_a.remaining_qty == pytest.approx(0.0)
    assert order_b.status == PositionOrderStatus.CLOSED
    assert order_b.remaining_qty == pytest.approx(0.0)
    assert order_c.status == PositionOrderStatus.PARTIAL
    assert order_c.remaining_qty == pytest.approx(0.5)

    assert position.qty == pytest.approx(0.5)

    matched = [(m.open_order_id, m.matched_qty) for m in result.matches]
    assert matched == [
        (order_a.id, pytest.approx(0.5)),
        (order_b.id, pytest.approx(0.3)),
        (order_c.id, pytest.approx(0.2)),
    ]

    expected_pnl = (
        (63000.0 - 60000.0) * 0.5
        + (63000.0 - 61000.0) * 0.3
        + (63000.0 - 62000.0) * 0.2
    )
    assert result.realized_pnl == pytest.approx(expected_pnl)
    assert result.execution.realized_pnl == pytest.approx(expected_pnl)
    assert result.execution.close_qty == pytest.approx(1.0)

    assert position.entry_price == pytest.approx(62000.0)
    assert position.unrealized_pnl == pytest.approx((51000.0 - 62000.0) * 0.5)


def test_short_side_realized_pnl_sign(in_memory_session: Session) -> None:
    """SHORT side: PnL = (entry - close) * qty."""

    position = _bootstrap_position(
        in_memory_session, side=PositionSide.SHORT, qty=2.0, mark_price=49000.0
    )
    _add_order(
        in_memory_session, position, open_qty=2.0, entry_price=50000.0
    )

    result = fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=1.0,
        close_price=49000.0,
    )

    assert result.realized_pnl == pytest.approx((50000.0 - 49000.0) * 1.0)
    in_memory_session.refresh(position)
    assert position.qty == pytest.approx(1.0)
    assert position.unrealized_pnl == pytest.approx((50000.0 - 49000.0) * 1.0)


def test_over_close_raises(in_memory_session: Session) -> None:
    position = _bootstrap_position(in_memory_session, qty=0.5)
    _add_order(
        in_memory_session, position, open_qty=0.5, entry_price=50000.0
    )

    with pytest.raises(FifoCloseError):
        fifo_close_position(
            in_memory_session,
            position_id=position.id,
            close_qty=1.0,
            close_price=51000.0,
        )


def test_non_positive_qty_raises(in_memory_session: Session) -> None:
    position = _bootstrap_position(in_memory_session, qty=1.0)
    _add_order(
        in_memory_session, position, open_qty=1.0, entry_price=50000.0
    )

    with pytest.raises(FifoCloseError):
        fifo_close_position(
            in_memory_session,
            position_id=position.id,
            close_qty=0.0,
            close_price=51000.0,
        )


def test_match_rows_persist_with_execution_link(
    in_memory_session: Session,
) -> None:
    """End-to-end: rows are queryable through the FK after the call."""

    position = _bootstrap_position(in_memory_session, qty=1.0)
    _add_order(
        in_memory_session, position, open_qty=1.0, entry_price=50000.0
    )

    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.4,
        close_price=52000.0,
    )
    in_memory_session.commit()

    executions = list(
        in_memory_session.exec(
            select(PositionCloseExecution).where(
                PositionCloseExecution.position_id == position.id
            )
        ).all()
    )
    assert len(executions) == 1
    execution = executions[0]
    assert execution.close_qty == pytest.approx(0.4)
    assert execution.realized_pnl == pytest.approx(800.0)

    matches = list(
        in_memory_session.exec(
            select(PositionOrderMatch).where(
                PositionOrderMatch.close_order_id == execution.id
            )
        ).all()
    )
    assert len(matches) == 1
    assert matches[0].realized_pnl == pytest.approx(800.0)
