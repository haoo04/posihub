"""PnL helpers for USDT-margined and coin-margined (inverse) positions."""

from __future__ import annotations

from ..db.models import AccountType, PositionSide


def base_asset_from_canonical(canonical_symbol: str) -> str:
    """Extract base asset from canonical symbols like ``BTC-USDT-PERP``."""

    head = (canonical_symbol or "").strip().upper().split("-")[0]
    return head or "?"


def is_coin_margined_account(account_type: AccountType) -> bool:
    return account_type == AccountType.COIN_PERP


def linear_unrealized_pnl_usdt(
    side: PositionSide, entry_price: float, mark_price: float, qty: float
) -> float:
    """Unrealized PnL in USDT when ``qty`` is underlying asset size."""

    if qty <= 0:
        return 0.0
    if side == PositionSide.LONG:
        return (mark_price - entry_price) * qty
    if side == PositionSide.SHORT:
        return (entry_price - mark_price) * qty
    return 0.0


def usdt_to_settlement_coin(pnl_usdt: float, mark_price: float) -> float:
    """Convert USDT PnL to settlement coin using ``mark_price``."""

    if mark_price <= 0:
        return 0.0
    return pnl_usdt / mark_price


def settlement_coin_to_usdt(pnl_coin: float, mark_price: float) -> float:
    """Convert settlement-coin PnL to USDT using ``mark_price``."""

    return pnl_coin * mark_price


def position_unrealized_pnl_usdt(
    *,
    account_type: AccountType | None,
    side: PositionSide,
    unrealized_pnl: float,
    mark_price: float,
    has_position_orders: bool,
) -> float:
    """Normalize position-level unrealized PnL to USDT for API responses.

    When order legs exist, unrealized PnL is already derived via the linear
    USDT formula. Otherwise, for coin-margined accounts synced from the
    exchange, the stored value is treated as settlement coin.
    """

    if account_type is None or not is_coin_margined_account(account_type):
        return unrealized_pnl
    if has_position_orders:
        return unrealized_pnl
    return settlement_coin_to_usdt(unrealized_pnl, mark_price)
