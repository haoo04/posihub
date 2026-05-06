"""Account + exchange management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..core.security import decrypt_secret, encrypt_secret, mask_secret
from ..db.models import Account, Exchange
from ..schemas.account import (
    AccountCreate,
    AccountRead,
    AccountSyncStatus,
    AccountUpdate,
)
from ..schemas.exchange import ExchangeCreate, ExchangeRead
from ..services.sync_service import sync_account, sync_account_by_id
from .deps import SessionDep

router = APIRouter(prefix="/api/v1", tags=["accounts"])


# ---------------------------------------------------------------------------
# Exchanges
# ---------------------------------------------------------------------------


@router.get("/exchanges", response_model=list[ExchangeRead])
def list_exchanges(session: SessionDep) -> list[Exchange]:
    return list(session.exec(select(Exchange)).all())


@router.post(
    "/exchanges",
    response_model=ExchangeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_exchange(payload: ExchangeCreate, session: SessionDep) -> Exchange:
    existing = session.exec(
        select(Exchange).where(Exchange.name == payload.name.lower())
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="exchange already exists")

    row = Exchange(name=payload.name.lower(), enabled=payload.enabled)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def _to_read(account: Account) -> AccountRead:
    api_key_plain = None
    try:
        api_key_plain = decrypt_secret(account.api_key_enc)
    except Exception:
        api_key_plain = None
    return AccountRead(
        id=account.id or 0,
        exchange_id=account.exchange_id,
        account_name=account.account_name,
        account_type=account.account_type,
        is_simulated=account.is_simulated,
        enabled=account.enabled,
        last_sync_at=account.last_sync_at,
        last_sync_status=account.last_sync_status,
        last_sync_error=account.last_sync_error,
        consecutive_failures=account.consecutive_failures,
        created_at=account.created_at,
        api_key_masked=mask_secret(api_key_plain) if api_key_plain else None,
    )


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(session: SessionDep) -> list[AccountRead]:
    rows = list(session.exec(select(Account)).all())
    return [_to_read(r) for r in rows]


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_account(payload: AccountCreate, session: SessionDep) -> AccountRead:
    exchange = session.get(Exchange, payload.exchange_id)
    if exchange is None:
        raise HTTPException(status_code=404, detail="exchange not found")

    account = Account(
        exchange_id=payload.exchange_id,
        account_name=payload.account_name,
        account_type=payload.account_type,
        api_key_enc=encrypt_secret(payload.api_key) if payload.api_key else None,
        api_secret_enc=encrypt_secret(payload.api_secret) if payload.api_secret else None,
        passphrase_enc=encrypt_secret(payload.passphrase) if payload.passphrase else None,
        is_simulated=payload.is_simulated,
        enabled=payload.enabled,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return _to_read(account)


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int, payload: AccountUpdate, session: SessionDep
) -> AccountRead:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        account.api_key_enc = encrypt_secret(data.pop("api_key"))
    if "api_secret" in data:
        account.api_secret_enc = encrypt_secret(data.pop("api_secret"))
    if "passphrase" in data:
        account.passphrase_enc = encrypt_secret(data.pop("passphrase"))

    for field, value in data.items():
        setattr(account, field, value)

    session.add(account)
    session.commit()
    session.refresh(account)
    return _to_read(account)


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_account(account_id: int, session: SessionDep) -> None:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    session.delete(account)
    session.commit()


@router.post("/accounts/{account_id}/sync", response_model=AccountSyncStatus)
def trigger_sync(account_id: int, session: SessionDep) -> AccountSyncStatus:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    if account.is_simulated:
        outcome = sync_account(session, account)
        session.commit()
    else:
        outcome = sync_account_by_id(account_id)

    return AccountSyncStatus(
        account_id=outcome.account_id,
        success=outcome.success,
        message=outcome.message,
        synced_at=outcome.synced_at,
    )
