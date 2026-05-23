"""Tests for spot vs derivatives position filtering."""

from __future__ import annotations

from app.db.models import Account, AccountType, PositionCurrent, PositionSide
from app.services.position_market import (
    instrument_type_from_canonical,
    position_matches_market,
)


def _account(account_type: AccountType) -> Account:
    return Account(
        id=1,
        exchange_id=1,
        account_name="test",
        account_type=account_type,
    )


def _position(canonical: str) -> PositionCurrent:
    return PositionCurrent(
        id=1,
        account_id=1,
        canonical_symbol=canonical,
        side=PositionSide.LONG,
        qty=1.0,
    )


def test_instrument_type_from_canonical() -> None:
    assert instrument_type_from_canonical("BTC-USDT-SPOT").value == "spot"
    assert instrument_type_from_canonical("BTC-USDT-PERP").value == "perp"


def test_spot_account_only_matches_spot_market() -> None:
    pos = _position("BTC-USDT-SPOT")
    acc = _account(AccountType.SPOT)
    assert position_matches_market(pos, acc, "spot") is True
    assert position_matches_market(pos, acc, "derivatives") is False


def test_perp_account_only_matches_derivatives_market() -> None:
    pos = _position("BTC-USDT-PERP")
    acc = _account(AccountType.USDT_PERP)
    assert position_matches_market(pos, acc, "derivatives") is True
    assert position_matches_market(pos, acc, "spot") is False


def test_simulated_uses_canonical_suffix() -> None:
    acc = _account(AccountType.SIMULATED)
    spot = _position("BTC-USDT-SPOT")
    perp = _position("BTC-USDT-PERP")
    assert position_matches_market(spot, acc, "spot") is True
    assert position_matches_market(perp, acc, "spot") is False
    assert position_matches_market(perp, acc, "derivatives") is True
