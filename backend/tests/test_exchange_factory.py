"""Tests for CCXT option resolution per account type."""

from __future__ import annotations

import ccxt

from app.db.models import Account, AccountType, Exchange
from app.services.exchange.ccxt_client import _build_exchange
from app.services.exchange.ccxt_client import bitget_fetch_params
from app.services.exchange.factory import resolve_ccxt_options


def _account(account_type: AccountType) -> Account:
    return Account(
        id=1,
        exchange_id=1,
        account_name="test",
        account_type=account_type,
    )


def test_resolve_ccxt_options_usdt_perp_is_linear_swap() -> None:
    opts = resolve_ccxt_options(_account(AccountType.USDT_PERP))
    assert opts.default_type == "swap"
    assert opts.default_sub_type == "linear"


def test_resolve_ccxt_options_coin_perp_is_inverse_swap() -> None:
    opts = resolve_ccxt_options(_account(AccountType.COIN_PERP))
    assert opts.default_type == "swap"
    assert opts.default_sub_type == "inverse"
    assert bitget_fetch_params("bitget", opts.default_sub_type) == {
        "productType": "COIN-FUTURES"
    }


def test_resolve_ccxt_options_spot_has_no_subtype() -> None:
    opts = resolve_ccxt_options(_account(AccountType.SPOT))
    assert opts.default_type == "spot"
    assert opts.default_sub_type is None


def test_build_exchange_bitget_coin_perp_sets_inverse() -> None:
    client = _build_exchange(
        "bitget",
        api_key=None,
        api_secret=None,
        passphrase=None,
        default_type="swap",
        default_sub_type="inverse",
    )
    assert client.options["defaultType"] == "swap"
    assert client.options["defaultSubType"] == "inverse"


def test_build_exchange_bitget_usdt_perp_sets_linear() -> None:
    client = _build_exchange(
        "bitget",
        api_key=None,
        api_secret=None,
        passphrase=None,
        default_type="swap",
        default_sub_type="linear",
    )
    assert client.options["defaultType"] == "swap"
    assert client.options["defaultSubType"] == "linear"


def test_bitget_swap_only_defaults_to_linear() -> None:
    """Document CCXT default: swap without subtype is USDT-margined on Bitget."""

    client = ccxt.bitget({"options": {"defaultType": "swap"}})
    assert client.options["defaultSubType"] == "linear"
