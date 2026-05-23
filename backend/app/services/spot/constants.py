"""Shared constants for spot position derivation."""

from __future__ import annotations

# Quote / stable assets excluded from spot holdings (Section 7 decision #2).
STABLECOIN_ASSETS: frozenset[str] = frozenset(
    {
        "USDT",
        "USDC",
        "BUSD",
        "FDUSD",
        "TUSD",
        "DAI",
        "USD",
        "EUR",
        "USDD",
        "PYUSD",
    }
)

# Preferred quote when building spot pairs for valuation.
QUOTE_PRIORITY: tuple[str, ...] = (
    "USDT",
    "USDC",
    "USD",
    "BUSD",
    "FDUSD",
    "TUSD",
    "DAI",
    "EUR",
)
