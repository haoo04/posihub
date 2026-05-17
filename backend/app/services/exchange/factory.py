"""Account-to-connector factory.

Translates an :class:`Account` ORM row into a configured
:class:`ExchangeClient`. Centralises secret decryption so callers never need
to handle plaintext API credentials directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, select

from ...core.security import decrypt_secret
from ...db.models import Account, AccountType, Exchange
from .base import ExchangeClient
from .ccxt_client import CcxtExchangeClient


_DEFAULT_TYPE_MAP: dict[AccountType, Optional[str]] = {
    AccountType.SPOT: "spot",
    AccountType.USDT_PERP: "swap",
    AccountType.COIN_PERP: "swap",
    AccountType.FUTURES: "future",
    AccountType.FUNDING: None,
    AccountType.SIMULATED: None,
}

# CCXT ``defaultSubType``: linear = USDT-margined swap, inverse = coin-margined.
_DEFAULT_SUBTYPE_MAP: dict[AccountType, Optional[str]] = {
    AccountType.USDT_PERP: "linear",
    AccountType.COIN_PERP: "inverse",
}


@dataclass(frozen=True, slots=True)
class CcxtAccountOptions:
    default_type: Optional[str] = None
    default_sub_type: Optional[str] = None


def resolve_ccxt_options(account: Account) -> CcxtAccountOptions:
    return CcxtAccountOptions(
        default_type=_DEFAULT_TYPE_MAP.get(account.account_type),
        default_sub_type=_DEFAULT_SUBTYPE_MAP.get(account.account_type),
    )


def resolve_default_type(account: Account) -> Optional[str]:
    """Return CCXT ``defaultType`` for the account (legacy helper)."""

    return resolve_ccxt_options(account).default_type


def build_client_for_account(session: Session, account: Account) -> ExchangeClient:
    """Build a CCXT-backed connector for the given account."""

    if account.is_simulated:
        raise ValueError("Cannot build exchange client for a simulated account")

    exchange = session.get(Exchange, account.exchange_id)
    if exchange is None:
        raise LookupError(f"Exchange #{account.exchange_id} not found")

    api_key = decrypt_secret(account.api_key_enc)
    api_secret = decrypt_secret(account.api_secret_enc)
    passphrase = decrypt_secret(account.passphrase_enc)

    ccxt_opts = resolve_ccxt_options(account)
    return CcxtExchangeClient(
        exchange_id=exchange.name,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        default_type=ccxt_opts.default_type,
        default_sub_type=ccxt_opts.default_sub_type,
    )


def get_account_or_404(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise LookupError(f"Account #{account_id} not found")
    return account


def list_active_accounts(session: Session) -> list[Account]:
    stmt = select(Account).where(Account.enabled == True)  # noqa: E712
    return list(session.exec(stmt).all())
