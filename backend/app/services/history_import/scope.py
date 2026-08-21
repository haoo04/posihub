"""Bitget product-scope checks used by history import.

Bitget exposes several contract products through the same API key.  CCXT's
``defaultSubType`` is useful for routing requests, but it is not a sufficient
data-integrity boundary: a response can still contain a symbol from another
product.  This module keeps the final, conservative checks in one place.
"""

from __future__ import annotations

from typing import Any

from ...db.models import AccountType

BITGET_LINEAR_PRODUCT = "USDT-FUTURES"
BITGET_INVERSE_PRODUCT = "COIN-FUTURES"


def expected_bitget_product_type(account_type: AccountType | None) -> str | None:
    if account_type == AccountType.USDT_PERP:
        return BITGET_LINEAR_PRODUCT
    if account_type == AccountType.COIN_PERP:
        return BITGET_INVERSE_PRODUCT
    return None


def expected_settlement_asset(account_type: AccountType | None) -> str | None:
    if account_type == AccountType.USDT_PERP:
        return "USDT"
    if account_type == AccountType.COIN_PERP:
        return "USD"
    return None


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _product_matches(value: Any, expected: str) -> bool | None:
    """Return ``True``/``False`` for a product marker, ``None`` if unknown."""

    text = _upper(value)
    if not text:
        return None
    aliases = {
        BITGET_LINEAR_PRODUCT: {BITGET_LINEAR_PRODUCT, "LINEAR", "USDT", "USDT-PERP"},
        BITGET_INVERSE_PRODUCT: {BITGET_INVERSE_PRODUCT, "INVERSE", "COIN", "COIN-PERP"},
    }
    if text in aliases[expected]:
        return True
    if any(text in values for product, values in aliases.items() if product != expected):
        return False
    # Explicit but unfamiliar product markers are safer to reject than to
    # silently mix accounts.  Common CCXT rows omit this field entirely.
    if "FUTURES" in text or text in {
        "LINEAR",
        "INVERSE",
        "COIN",
        "USDT",
        "SPOT",
        "MARGIN",
        "FUNDING",
    }:
        return False
    return None


def _symbol_matches_settlement(symbol: Any, expected_settle: str) -> bool | None:
    text = _upper(symbol)
    if not text:
        return None
    if "/" in text:
        pair, _, settle = text.partition(":")
        _, _, quote = pair.partition("/")
        if quote and quote != expected_settle:
            return False
        if settle and expected_settle == "USDT" and settle != "USDT":
            return False
        if settle and expected_settle == "USD" and settle == "USDT":
            return False
        return True
    # Canonical/compact symbols are useful only for the unambiguous stable
    # suffixes.  A coin settlement suffix is usually the base asset and cannot
    # be inferred from a bare string, so leave it to the canonical mapper.
    if text.endswith("USDT"):
        return expected_settle == "USDT"
    if text.endswith("-USDT-PERP"):
        return expected_settle == "USDT"
    if text.endswith("-USD-PERP"):
        return expected_settle == "USD"
    return None


def raw_matches_bitget_product(
    raw: dict[str, Any] | None,
    account_type: AccountType | None,
) -> bool:
    """Check raw Bitget/CCXT metadata against the requested account.

    Missing metadata is allowed here because older CCXT payloads only carry a
    symbol.  The canonical-symbol check performed after mapping is mandatory
    whenever an account type is known.
    """

    expected = expected_bitget_product_type(account_type)
    if expected is None or not isinstance(raw, dict):
        return True

    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    product_values = [
        raw.get("productType"),
        raw.get("product_type"),
        raw.get("category"),
        info.get("productType"),
        info.get("product_type"),
        info.get("category"),
    ]
    for value in product_values:
        match = _product_matches(value, expected)
        if match is False:
            return False
        if match is True:
            break

    expected_settle = expected_settlement_asset(account_type)
    margin_values = [raw.get("marginCoin"), info.get("marginCoin")]
    settle_values = [
        raw.get("settle"),
        raw.get("settleCoin"),
        raw.get("settlementCoin"),
        info.get("settle"),
        info.get("settleCoin"),
        info.get("settlementCoin"),
    ]
    if expected_settle == "USDT":
        if any(_upper(value) not in {"", "USDT"} for value in margin_values):
            return False
        if any(_upper(value) not in {"", "USDT"} for value in settle_values):
            return False
    elif expected_settle == "USD":
        if any(_upper(value) == "USDT" for value in margin_values + settle_values):
            return False

    symbol_values = [raw.get("symbol"), info.get("symbol")]
    for symbol in symbol_values:
        match = _symbol_matches_settlement(symbol, expected_settle or "")
        if match is False:
            return False

    return True


def canonical_matches_bitget_product(
    canonical_symbol: str | None,
    account_type: AccountType | None,
) -> bool:
    """Require the canonical perpetual quote to match the account product."""

    expected = expected_settlement_asset(account_type)
    if expected is None:
        return True
    canonical = _upper(canonical_symbol)
    return canonical.endswith(f"-{expected}-PERP")
