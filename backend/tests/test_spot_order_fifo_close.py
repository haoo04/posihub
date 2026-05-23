"""Spot FIFO close reuses derivative long-side matching."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.db.models import (
    Account,
    AccountType,
    Exchange,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
)
from app.services.position_order_close import fifo_close_position


def _seed_spot_position(session: Session) -> PositionCurrent:
    exch = Exchange(name="binance", enabled=True)
    session.add(exch)
    session.commit()
    session.refresh(exch)

    account = Account(
        exchange_id=exch.id,
        account_name="spot",
        account_type=AccountType.SPOT,
        enabled=True,
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    position = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USDT-SPOT",
        side=PositionSide.LONG,
        qty=1.0,
        entry_price=50_000.0,
        mark_price=52_000.0,
        unrealized_pnl=2_000.0,
        leverage=1.0,
        updated_at=datetime(2026, 1, 1),
    )
    session.add(position)
    session.commit()
    session.refresh(position)

    session.add(
        PositionOrder(
            position_id=position.id,
            open_qty=1.0,
            remaining_qty=1.0,
            entry_price=50_000.0,
            leverage=1.0,
            status=PositionOrderStatus.OPEN,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
    )
    session.commit()
    return position


def test_spot_fifo_close_realized_pnl(in_memory_session: Session) -> None:
    position = _seed_spot_position(in_memory_session)

    pid = int(position.id or 0)

    result = fifo_close_position(
        in_memory_session,
        position_id=pid,
        close_qty=0.5,
        close_price=52_000.0,
    )
    in_memory_session.commit()

    assert result.realized_pnl == 1_000.0

    refreshed = in_memory_session.get(PositionCurrent, pid)
    assert refreshed is not None
    assert refreshed.qty == 0.5
    assert refreshed.entry_price == 50_000.0

    order = in_memory_session.exec(select(PositionOrder)).one()
    assert order.remaining_qty == 0.5
    assert order.status == PositionOrderStatus.PARTIAL
