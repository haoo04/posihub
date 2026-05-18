"""Tests for stable-id upsert of current balances and positions."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.db.models import (
    AccountBalanceCurrent,
    DataSource,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
)
from app.services.normalize.normalizer import (
    NormalizedBalance,
    NormalizedPosition,
    upsert_balances,
    upsert_positions,
)


def _balance(
    asset: str = "USDT",
    equity: float = 100.0,
    *,
    account_id: int = 1,
) -> NormalizedBalance:
    return NormalizedBalance(
        account_id=account_id,
        asset=asset,
        equity=equity,
        available=equity,
        frozen=0.0,
        source=DataSource.API,
        updated_at=datetime(2026, 1, 1),
    )


def _position(
    *,
    canonical: str = "BTC-USDT-PERP",
    side: PositionSide = PositionSide.LONG,
    qty: float = 1.0,
    entry: float = 30_000.0,
    account_id: int = 1,
) -> NormalizedPosition:
    return NormalizedPosition(
        account_id=account_id,
        canonical_symbol=canonical,
        side=side,
        qty=qty,
        entry_price=entry,
        mark_price=entry + 500.0,
        unrealized_pnl=100.0,
        leverage=1.0,
        margin_mode=None,
        source=DataSource.API,
        updated_at=datetime(2026, 1, 1),
    )


def test_upsert_balances_preserves_id_on_resync(in_memory_session: Session) -> None:
    upsert_balances(in_memory_session, 1, [_balance(equity=100.0)])
    in_memory_session.commit()
    first = in_memory_session.exec(select(AccountBalanceCurrent)).one()
    first_id = first.id

    upsert_balances(in_memory_session, 1, [_balance(equity=200.0)])
    in_memory_session.commit()
    second = in_memory_session.exec(select(AccountBalanceCurrent)).one()

    assert second.id == first_id
    assert second.equity == 200.0


def test_upsert_balances_removes_stale_assets(in_memory_session: Session) -> None:
    upsert_balances(
        in_memory_session,
        1,
        [_balance(asset="USDT"), _balance(asset="BTC", equity=0.5)],
    )
    in_memory_session.commit()

    upsert_balances(in_memory_session, 1, [_balance(asset="USDT")])
    in_memory_session.commit()

    assets = {
        row.asset
        for row in in_memory_session.exec(select(AccountBalanceCurrent)).all()
    }
    assert assets == {"USDT"}


def test_upsert_positions_preserves_id_on_resync(in_memory_session: Session) -> None:
    upsert_positions(in_memory_session, 1, [_position(qty=1.0, entry=30_000.0)])
    in_memory_session.commit()
    first = in_memory_session.exec(select(PositionCurrent)).one()
    first_id = first.id

    upsert_positions(in_memory_session, 1, [_position(qty=2.0, entry=31_000.0)])
    in_memory_session.commit()
    second = in_memory_session.exec(select(PositionCurrent)).one()

    assert second.id == first_id
    assert second.qty == 2.0
    assert second.entry_price == 31_000.0


def test_upsert_positions_deletes_stale_row_without_orders(
    in_memory_session: Session,
) -> None:
    upsert_positions(
        in_memory_session,
        1,
        [
            _position(canonical="BTC-USDT-PERP"),
            _position(canonical="ETH-USDT-PERP", entry=2000.0),
        ],
    )
    in_memory_session.commit()

    upsert_positions(in_memory_session, 1, [_position(canonical="BTC-USDT-PERP")])
    in_memory_session.commit()

    rows = list(in_memory_session.exec(select(PositionCurrent)).all())
    assert len(rows) == 1
    assert rows[0].canonical_symbol == "BTC-USDT-PERP"


def test_upsert_positions_zeroes_stale_row_when_orders_exist(
    in_memory_session: Session,
) -> None:
    upsert_positions(in_memory_session, 1, [_position(qty=1.0)])
    in_memory_session.commit()
    position = in_memory_session.exec(select(PositionCurrent)).one()
    assert position.id is not None

    in_memory_session.add(
        PositionOrder(
            position_id=position.id,
            open_qty=1.0,
            remaining_qty=1.0,
            entry_price=30_000.0,
            status=PositionOrderStatus.OPEN,
        )
    )
    in_memory_session.commit()

    upsert_positions(in_memory_session, 1, [])
    in_memory_session.commit()

    row = in_memory_session.exec(select(PositionCurrent)).one()
    assert row.id == position.id
    assert row.qty == 0.0
    assert row.unrealized_pnl == 0.0

    order = in_memory_session.exec(select(PositionOrder)).one()
    assert order.position_id == position.id
