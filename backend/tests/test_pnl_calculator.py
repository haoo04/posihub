"""Tests for PnL calculator helpers."""

from __future__ import annotations

import pytest

from app.db.models import AccountType, PositionSide
from app.services.exchange.base import RawPosition
from app.services.normalize.normalizer import normalize_positions
from app.services.normalize.symbol_mapper import CanonicalSymbol
from app.services.pnl_calculator import (
    base_asset_from_canonical,
    linear_unrealized_pnl_usdt,
    position_unrealized_pnl_usdt,
    raw_position_unrealized_pnl_to_usdt,
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


def test_position_unrealized_coin_is_already_canonical_usdt() -> None:
    upnl = position_unrealized_pnl_usdt(
        account_type=AccountType.COIN_PERP,
        side=PositionSide.LONG,
        unrealized_pnl=0.01,
        mark_price=50000.0,
        has_position_orders=False,
    )
    assert upnl == pytest.approx(0.01)


def test_position_unrealized_coin_with_orders_unchanged() -> None:
    upnl = position_unrealized_pnl_usdt(
        account_type=AccountType.COIN_PERP,
        side=PositionSide.LONG,
        unrealized_pnl=600.0,
        mark_price=50000.0,
        has_position_orders=True,
    )
    assert upnl == pytest.approx(600.0)


def test_raw_coin_position_is_converted_once_at_sync_boundary() -> None:
    assert raw_position_unrealized_pnl_to_usdt(
        account_type=AccountType.COIN_PERP,
        unrealized_pnl=-3.2282 / 1907.82,
        mark_price=1907.82,
    ) == pytest.approx(-3.2282, abs=1e-4)


def test_raw_coin_position_with_empty_mark_is_zero() -> None:
    assert raw_position_unrealized_pnl_to_usdt(
        account_type=AccountType.COIN_PERP,
        unrealized_pnl=0.01,
        mark_price=0.0,
    ) == 0.0


def test_normalize_positions_stores_coin_pnl_as_usdt() -> None:
    class Mapper:
        def resolve(self, exchange, raw_symbol, **kwargs):
            return CanonicalSymbol(
                canonical="ETH-USD-PERP",
                base_asset="ETH",
                quote_asset="USD",
                instrument_type="perp",
            )

    rows = normalize_positions(
        account_id=1,
        exchange_name="bitget",
        raws=[
            RawPosition(
                raw_symbol="ETH/USD:ETH",
                side="long",
                qty=0.01,
                entry_price=1585.0,
                mark_price=1907.82,
                unrealized_pnl=-3.2282 / 1907.82,
            )
        ],
        mapper=Mapper(),
        account_type=AccountType.COIN_PERP,
    )
    assert rows[0].unrealized_pnl == pytest.approx(-3.2282, abs=1e-4)
