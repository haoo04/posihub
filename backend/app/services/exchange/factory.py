"""Account-to-connector factory.

Translates an :class:`Account` ORM row into a configured
:class:`ExchangeClient`. Centralises secret decryption so callers never need
to handle plaintext API credentials directly.
"""

from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from ...core.security import decrypt_secret
from ...db.models import Account, AccountType, Exchange
from .base import ExchangeClient
from .ccxt_client import CcxtExchangeClient


_DEFAULT_TYPE_MAP = {
    AccountType.SPOT: "spot",
    AccountType.USDT_PERP: "swap",
    AccountType.COIN_PERP: "swap",
    AccountType.FUTURES: "future",
    AccountType.FUNDING: None,
    AccountType.SIMULATED: None,
}


def resolve_default_type(account: Account) -> Optional[str]:
    return _DEFAULT_TYPE_MAP.get(account.account_type)


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

    return CcxtExchangeClient(
        exchange_id=exchange.name,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        default_type=resolve_default_type(account),
    )


def get_account_or_404(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise LookupError(f"Account #{account_id} not found")
    return account


def list_active_accounts(session: Session) -> list[Account]:
    stmt = select(Account).where(Account.enabled == True)  # noqa: E712
    return list(session.exec(stmt).all())
