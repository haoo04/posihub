"""Committer integration tests: writes ledger rows and is idempotent."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.db.models import (
    Account,
    AccountType,
    Exchange,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionOrderMatch,
    PositionOrderStatus,
    PositionSide,
)
from app.services.history_import.committer import commit_history_import
from app.services.history_import.types import ImportAction, NormalizedHistoryOrder

_BASE = datetime(2026, 1, 1, 0, 0, 0)


def _bootstrap_account(session: Session) -> Account:
    exchange = Exchange(name="bitget")
    session.add(exchange)
    session.flush()
    account = Account(
        exchange_id=exchange.id,
        account_name="bitget-perp",
        account_type=AccountType.USDT_PERP,
    )
    session.add(account)
    session.flush()
    return account


def _order(sid, action, qty, price, minute) -> NormalizedHistoryOrder:
    return NormalizedHistoryOrder(
        source_order_id=sid,
        raw_symbol="ETH/USDT:USDT",
        canonical_symbol="ETH-USDT-PERP",
        side=PositionSide.LONG,
        action=action,
        qty=qty,
        price=price,
        created_at=_BASE + timedelta(minutes=minute),
    )


def test_commit_creates_orders_executions_matches(in_memory_session: Session) -> None:
    account = _bootstrap_account(in_memory_session)
    orders = [
        _order("o1", ImportAction.OPEN, 1.0, 2000.0, 0),
        _order("o2", ImportAction.OPEN, 1.0, 2200.0, 1),
        _order("c1", ImportAction.CLOSE, 1.5, 2300.0, 2),
    ]

    result = commit_history_import(
        in_memory_session, account_id=account.id, orders=orders
    )
    in_memory_session.commit()

    assert result.created_opens == 2
    assert result.created_closes == 1

    position = in_memory_session.exec(
        select(PositionCurrent).where(PositionCurrent.account_id == account.id)
    ).first()
    assert position is not None
    # 2.0 opened, 1.5 closed -> 0.5 remaining.
    assert abs(position.qty - 0.5) < 1e-9

    pos_orders = in_memory_session.exec(
        select(PositionOrder).where(PositionOrder.position_id == position.id)
    ).all()
    assert len(pos_orders) == 2
    statuses = {o.source_order_id: o.status for o in pos_orders}
    assert statuses["o1"] == PositionOrderStatus.CLOSED
    assert statuses["o2"] == PositionOrderStatus.PARTIAL

    executions = in_memory_session.exec(select(PositionCloseExecution)).all()
    assert len(executions) == 1
    matches = in_memory_session.exec(select(PositionOrderMatch)).all()
    # o1 fully (1.0) + o2 partially (0.5) = 2 match rows.
    assert len(matches) == 2
    # LONG realized: (2300-2000)*1.0 + (2300-2200)*0.5 = 350
    assert abs(sum(m.realized_pnl for m in matches) - 350.0) < 1e-9


def test_commit_is_idempotent(in_memory_session: Session) -> None:
    account = _bootstrap_account(in_memory_session)
    orders = [
        _order("o1", ImportAction.OPEN, 1.0, 2000.0, 0),
        _order("c1", ImportAction.CLOSE, 1.0, 2100.0, 1),
    ]

    first = commit_history_import(
        in_memory_session, account_id=account.id, orders=orders
    )
    in_memory_session.commit()
    assert first.created_opens == 1
    assert first.created_closes == 1

    # Re-running the same import must not duplicate anything.
    second = commit_history_import(
        in_memory_session, account_id=account.id, orders=orders
    )
    in_memory_session.commit()
    assert second.created_opens == 0
    assert second.created_closes == 0
    assert second.skipped == 2

    pos_orders = in_memory_session.exec(select(PositionOrder)).all()
    assert len(pos_orders) == 1
    executions = in_memory_session.exec(select(PositionCloseExecution)).all()
    assert len(executions) == 1
