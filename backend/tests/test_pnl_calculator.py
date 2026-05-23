"""Tests for PnL calculator helpers."""

from __future__ import annotations

import pytest

from app.db.models import AccountType, PositionSide
from app.services.pnl_calculator import (
    base_asset_from_canonical,
    linear_unrealized_pnl_usdt,
    position_unrealized_pnl_usdt,
    usdt_to_settlement_coin,
)


def test_base_asset_from_canonical() -> None:
    assert base_asset_from_canonical("BTC-USD-PERP") == "BTC"


def test_linear_unrealized_long() -> None:
    pnl = linear_unrealized_pnl_usdt(
        PositionSide.LONG, entry_price=50000.0, mark_price=51000.0, qty=0.5
    )
    assert pnl == pytest.approx(500.0)


def test_usdt_to_settlement_coin() -> None:
    native = usdt_to_settlement_coin(510.0, mark_price=51000.0)
    assert native == pytest.approx(0.01)


def test_position_unrealized_coin_without_orders() -> None:
    upnl = position_unrealized_pnl_usdt(
        account_type=AccountType.COIN_PERP,
        side=PositionSide.LONG,
        unrealized_pnl=0.01,
        mark_price=50000.0,
        has_position_orders=False,
    )
    assert upnl == pytest.approx(500.0)


def test_position_unrealized_coin_with_orders_unchanged() -> None:
    upnl = position_unrealized_pnl_usdt(
        account_type=AccountType.COIN_PERP,
        side=PositionSide.LONG,
        unrealized_pnl=600.0,
        mark_price=50000.0,
        has_position_orders=True,
    )
    assert upnl == pytest.approx(600.0)
