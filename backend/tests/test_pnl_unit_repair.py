"""Idempotent migration tests for legacy inverse PnL rows."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import (
    Account,
    AccountSnapshotDaily,
    AccountType,
    DataSource,
    Exchange,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
    PositionSnapshotDaily,
)
from app.services.pnl_unit_repair import repair_coin_pnl_units


def test_coin_pnl_repair_is_dry_run_safe_and_idempotent(in_memory_session) -> None:
    exchange = Exchange(name="bitget")
    in_memory_session.add(exchange)
    in_memory_session.flush()
    account = Account(
        exchange_id=exchange.id,
        account_name="coin",
        account_type=AccountType.COIN_PERP,
    )
    in_memory_session.add(account)
    in_memory_session.flush()

    legacy = PositionCurrent(
        account_id=account.id,
        canonical_symbol="ETH-USD-PERP",
        side=PositionSide.LONG,
        qty=0.01,
        entry_price=1585.0,
        mark_price=50_000.0,
        unrealized_pnl=0.01,
        source=DataSource.API,
    )
    with_children = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USD-PERP",
        side=PositionSide.LONG,
        qty=1.0,
        mark_price=50_000.0,
        unrealized_pnl=600.0,
        source=DataSource.API,
    )
    in_memory_session.add(legacy)
    in_memory_session.add(with_children)
    in_memory_session.flush()
    in_memory_session.add(
        PositionOrder(
            position_id=with_children.id,
            source=DataSource.API,
            source_order_id="already-usdt",
            status=PositionOrderStatus.OPEN,
            open_qty=1.0,
            remaining_qty=1.0,
            entry_price=49_400.0,
        )
    )
    snapshot_date = date(2026, 8, 20)
    in_memory_session.add(
        PositionSnapshotDaily(
            snapshot_date=snapshot_date,
            account_id=account.id,
            canonical_symbol="ETH-USD-PERP",
            side=PositionSide.LONG,
            qty=0.01,
            mark_price=50_000.0,
            unrealized_pnl=0.01,
            source=DataSource.API,
        )
    )
    in_memory_session.add(
        AccountSnapshotDaily(
            snapshot_date=snapshot_date,
            account_id=account.id,
            asset="USDT",
            total_unrealized_pnl=0.01,
            source=DataSource.API,
        )
    )
    in_memory_session.commit()

    dry = repair_coin_pnl_units(in_memory_session, dry_run=True)
    assert dry.current_positions == 1
    assert dry.position_snapshots == 1
    in_memory_session.refresh(legacy)
    assert legacy.unrealized_pnl == pytest.approx(0.01)

    applied = repair_coin_pnl_units(in_memory_session, dry_run=False)
    in_memory_session.commit()
    in_memory_session.refresh(legacy)
    in_memory_session.refresh(with_children)
    assert applied.current_positions == 1
    assert legacy.unrealized_pnl == pytest.approx(500.0)
    assert with_children.unrealized_pnl == pytest.approx(600.0)

    second = repair_coin_pnl_units(in_memory_session, dry_run=False)
    assert second.already_applied is True
    assert second.current_positions == 0
