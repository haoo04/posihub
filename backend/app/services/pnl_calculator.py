"""PnL helpers for USDT-margined and coin-margined (inverse) positions."""

from __future__ import annotations

from math import isfinite

from sqlmodel import Session

from ..db.models import Account, AccountType, Exchange, PositionSide


def quantity_context(
    exchange_name: str,
    account_type: AccountType | None,
    canonical_symbol: str,
    *,
    validate: bool = False,
) -> dict[str, str]:
    parts = canonical_symbol.upper().split("-")
    bybit_coin = exchange_name.lower() == "bybit" and account_type == AccountType.COIN_PERP
    inverse = bybit_coin and len(parts) == 3 and parts[1:] == ["USD", "PERP"]
    if validate and bybit_coin and not inverse:
        raise ValueError("Bybit coin_perp quantities require a *-USD-PERP symbol")
    return {
        "quantity_mode": "quote_contract" if inverse else "base",
        "quantity_unit": "USD" if inverse else base_asset_from_canonical(canonical_symbol),
    }


def get_quantity_context(
    session: Session,
    account_id: int,
    canonical_symbol: str,
    *,
    validate: bool = False,
) -> dict[str, str]:
    account = session.get(Account, account_id)
    exchange = session.get(Exchange, account.exchange_id) if account else None
    if validate and (account is None or exchange is None):
        raise ValueError("Quantity context requires an existing account and exchange")
    return quantity_context(
        exchange.name if exchange else "",
        account.account_type if account else None,
        canonical_symbol,
        validate=validate,
    )


def quote_qty_tolerance(entry_price: float) -> float:
    """USD tolerance covering legacy entry quantities rounded to eight decimals."""
    return max(1e-9, abs(entry_price) * 1e-8)


def normalize_quote_qty(qty: float, tolerance: float) -> float:
    nearest = round(qty)
    return float(nearest) if nearest != 0 and abs(qty - nearest) <= tolerance + 1e-12 else qty


def quote_to_entry_base(qty: float, entry_price: float) -> float:
    if not isfinite(entry_price) or entry_price <= 0:
        raise ValueError("Bybit inverse quantity conversion requires a positive entry_price")
    if not isfinite(qty) or qty < 0:
        raise ValueError("Quantity must be finite and non-negative")
    return qty / entry_price


def entry_base_to_quote(qty: float, entry_price: float) -> float:
    if qty == 0:
        return 0.0
    if not isfinite(entry_price) or entry_price <= 0:
        raise ValueError("Bybit inverse quantity conversion requires a positive entry_price")
    return normalize_quote_qty(qty * entry_price, quote_qty_tolerance(entry_price))


def inverse_pnl_coin(
    side: PositionSide,
    quote_qty: float,
    entry_price: float,
    exit_price: float,
) -> float:
    if entry_price <= 0 or exit_price <= 0:
        raise ValueError("Inverse PnL requires positive entry and exit prices")
    pnl = quote_qty * (1 / entry_price - 1 / exit_price)
    return pnl if side == PositionSide.LONG else -pnl if side == PositionSide.SHORT else 0.0


def base_asset_from_canonical(canonical_symbol: str) -> str:
    """Extract base asset from canonical symbols like ``BTC-USDT-PERP``."""

    head = (canonical_symbol or "").strip().upper().split("-")[0]
    return head or "?"


def is_coin_margined_account(account_type: AccountType) -> bool:
    return account_type == AccountType.COIN_PERP


def linear_unrealized_pnl_usdt(
    side: PositionSide, entry_price: float, mark_price: float, qty: float
) -> float:
    """USDT PnL for base size, or the inverse accounting size ``Q / entry``.

    For inverse legs this equals native coin PnL converted at the mark price.
    """

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


def raw_position_unrealized_pnl_to_usdt(
    *,
    account_type: AccountType | None,
    unrealized_pnl: float,
    mark_price: float,
) -> float:
    """Convert one exchange position response into the storage unit (USDT).

    Coin-margined inverse endpoints report PnL in the contract settlement coin;
    linear endpoints report it in USDT.  This is the single sync-boundary
    conversion.  ``positions_current.unrealized_pnl`` and all API/snapshot
    values are otherwise already USDT.
    """

    if account_type is not None and is_coin_margined_account(account_type):
        return settlement_coin_to_usdt(unrealized_pnl, mark_price)
    return unrealized_pnl


def position_unrealized_pnl_usdt(
    *,
    account_type: AccountType | None,
    side: PositionSide,
    unrealized_pnl: float,
    mark_price: float,
    has_position_orders: bool | None = None,
) -> float:
    """Return the canonical stored position PnL in USDT.

    ``has_position_orders`` remains accepted for source compatibility with
    older callers, but is intentionally ignored.  Inferring units from child
    rows was the source of the coin-margined dashboard bug.
    """

    del account_type, side, mark_price, has_position_orders
    return unrealized_pnl
