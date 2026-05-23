"""Filter positions by market (spot vs derivatives)."""

from __future__ import annotations

from ..db.models import Account, AccountType, InstrumentType, PositionCurrent


DERIVATIVE_ACCOUNT_TYPES: frozenset[AccountType] = frozenset(
    {
        AccountType.USDT_PERP,
        AccountType.COIN_PERP,
        AccountType.FUTURES,
    }
)

SPOT_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({AccountType.SPOT})


def instrument_type_from_canonical(canonical_symbol: str) -> InstrumentType:
    upper = (canonical_symbol or "").upper()
    if upper.endswith("-SPOT"):
        return InstrumentType.SPOT
    if upper.endswith("-FUTURES"):
        return InstrumentType.FUTURES
    if upper.endswith("-PERP"):
        return InstrumentType.PERP
    return InstrumentType.PERP


def instrument_hint_for_account(account_type: AccountType) -> str:
    if account_type == AccountType.SPOT:
        return InstrumentType.SPOT.value
    if account_type == AccountType.FUTURES:
        return InstrumentType.FUTURES.value
    return InstrumentType.PERP.value


def position_matches_market(
    position: PositionCurrent,
    account: Account | None,
    market: str,
) -> bool:
    """Return whether ``position`` belongs to ``market`` (``spot`` | ``derivatives``)."""

    instrument = instrument_type_from_canonical(position.canonical_symbol)
    account_type = account.account_type if account else None

    if market == "spot":
        if account_type == AccountType.SPOT:
            return True
        if account_type == AccountType.SIMULATED:
            return instrument == InstrumentType.SPOT
        if account_type in DERIVATIVE_ACCOUNT_TYPES:
            return False
        return instrument == InstrumentType.SPOT

    if market == "derivatives":
        if account_type in DERIVATIVE_ACCOUNT_TYPES:
            return True
        if account_type == AccountType.SPOT:
            return False
        if account_type == AccountType.SIMULATED:
            return instrument != InstrumentType.SPOT
        return instrument != InstrumentType.SPOT

    return True
