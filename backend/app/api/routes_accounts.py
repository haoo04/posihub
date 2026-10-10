"""Account + exchange management endpoints."""

from __future__ import annotations

import json
import time
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, select

from ..core.security import decrypt_secret, encrypt_secret, mask_secret
from ..db.models import Account, AccountType, Exchange, ExchangeConnectionState, HistoryImportPreview
from ..schemas.account import (
    AccountCreate,
    AccountRead,
    AccountSyncStatus,
    AccountUpdate,
)
from ..schemas.exchange import (
    ExchangeConnectionRead,
    ExchangeCreate,
    ExchangeRead,
)
from ..services.exchange.factory import build_client_for_account
from ..services.sync_service import sync_account, sync_account_by_id
from ..services.performance.equity_metrics import uta_basis_start_date
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


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _connection_read(
    account: Account,
    exchange: Exchange | None,
    state: ExchangeConnectionState | None,
) -> ExchangeConnectionRead:
    account_read = _to_read(account)
    if account.is_simulated:
        connection_status = "simulated"
    elif not account.api_key_enc or not account.api_secret_enc:
        connection_status = "not_configured"
    elif state is None:
        connection_status = "unknown"
    else:
        connection_status = state.status

    stored = json.loads(state.details_json or "{}") if state else {}
    safe_details = {
        key: stored[key]
        for key in ("account_mode", "account_level", "hold_mode", "permission_type", "permissions", "capabilities")
        if key in stored
    }
    if uid := stored.get("uid"):
        safe_details["uid_masked"] = "***" + str(uid)[-4:] if len(str(uid)) > 4 else "***"
    return ExchangeConnectionRead(
        account_id=int(account.id or 0),
        exchange_id=account.exchange_id,
        exchange_name=exchange.name if exchange else f"#{account.exchange_id}",
        account_name=account.account_name,
        account_type=account.account_type,
        enabled=account.enabled,
        is_simulated=account.is_simulated,
        api_key_masked=account_read.api_key_masked,
        status=connection_status,
        last_test_at=state.last_test_at if state else None,
        latency_ms=state.latency_ms if state else None,
        message=state.message if state else None,
        details=safe_details or None,
        blockers=stored.get("blockers", []),
        warnings=stored.get("warnings", []),
    )


@router.get(
    "/exchange-connections", response_model=list[ExchangeConnectionRead]
)
def list_exchange_connections(session: SessionDep) -> list[ExchangeConnectionRead]:
    """Return the latest read-only API connection state for every account."""

    exchanges = {
        int(row.id): row
        for row in session.exec(select(Exchange)).all()
        if row.id is not None
    }
    states = {
        int(row.account_id): row
        for row in session.exec(select(ExchangeConnectionState)).all()
    }
    accounts = list(session.exec(select(Account)).all())
    accounts.sort(key=lambda row: (row.exchange_id, row.account_name.lower()))
    return [_connection_read(row, exchanges.get(row.exchange_id), states.get(row.id or 0)) for row in accounts]


@router.post(
    "/exchange-connections/{account_id}/test",
    response_model=ExchangeConnectionRead,
)
def test_exchange_connection(
    account_id: int, session: SessionDep
) -> ExchangeConnectionRead:
    """Probe one account's private balance endpoint without changing account data."""

    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    exchange = session.get(Exchange, account.exchange_id)
    if exchange is None:
        raise HTTPException(status_code=404, detail="exchange not found")

    started = time.perf_counter()
    checked_at = _utcnow()
    connection_status = "connected"
    message = "ok"
    latency_ms: float | None = None
    client = None
    details = {}
    previous_state = session.exec(select(ExchangeConnectionState).where(ExchangeConnectionState.account_id == account_id)).first()
    previous_details = json.loads(previous_state.details_json or "{}") if previous_state else {}
    owner_uid = previous_details.get("owner_uid")
    if not owner_uid and previous_state and previous_state.status == "connected":
        owner_uid = previous_details.get("uid")

    if account.is_simulated:
        connection_status = "simulated"
        message = "simulated account does not use an exchange API"
    elif not account.api_key_enc or not account.api_secret_enc:
        connection_status = "not_configured"
        message = "api_key and api_secret are required"
    else:
        secrets_to_mask: list[str] = []
        for encrypted in (
            account.api_key_enc,
            account.api_secret_enc,
            account.passphrase_enc,
        ):
            try:
                plain = decrypt_secret(encrypted)
            except Exception:
                plain = None
            if plain:
                secrets_to_mask.append(plain)
        try:
            client = build_client_for_account(session, account)
            if exchange.name == "bitget":
                details = client.fetch_account_details()
            if account.account_type != AccountType.BITGET_UTA:
                client.fetch_balance()
            if details.get("blockers"):
                connection_status = "error"
                message = "; ".join(details["blockers"])
            if account.account_type == AccountType.BITGET_UTA and owner_uid and details.get("uid") != owner_uid:
                details.setdefault("blockers", []).append("These credentials belong to a different Bitget UID; create a separate account")
                connection_status = "error"
                message = "; ".join(details["blockers"])
            if exchange.name == "bitget" and details.get("uid"):
                others = session.exec(select(Account).where(
                    Account.exchange_id == account.exchange_id,
                    Account.id != account.id,
                    Account.enabled == True,
                    Account.is_simulated == False,
                )).all()
                for other in others:
                    if AccountType.BITGET_UTA not in (account.account_type, other.account_type):
                        continue
                    other_state = session.exec(select(ExchangeConnectionState).where(
                        ExchangeConnectionState.account_id == other.id
                    )).first()
                    other_uid = json.loads(other_state.details_json or "{}").get("uid") if other_state else None
                    if not other_uid or other_uid == details["uid"]:
                        details.setdefault("blockers", []).append(
                            f"Bitget account #{other.id} must be tested or disabled before this mode can be enabled"
                        )
                if details.get("blockers"):
                    connection_status = "error"
                    message = "; ".join(details["blockers"])
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except Exception as exc:
            connection_status = "error"
            detail = str(exc).strip() or exc.__class__.__name__
            for secret in secrets_to_mask:
                detail = detail.replace(secret, "***")
            message = f"{exc.__class__.__name__}: {detail[:450]}"
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        finally:
            if client is not None:
                with suppress(Exception):
                    client.close()

    state = session.exec(
        select(ExchangeConnectionState).where(
            ExchangeConnectionState.account_id == account_id
        )
    ).first()
    if state is None:
        state = ExchangeConnectionState(account_id=account_id)
    state.status = connection_status
    state.last_test_at = checked_at
    state.latency_ms = latency_ms
    state.message = message[:500]
    if account.account_type == AccountType.BITGET_UTA and (owner_uid or connection_status == "connected"):
        details["owner_uid"] = owner_uid or details.get("uid")
    state.details_json = json.dumps(details) if details else None
    session.add(state)
    session.commit()
    session.refresh(state)
    return _connection_read(account, exchange, state)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def _to_read(account: Account, session: Session | None = None) -> AccountRead:
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
        current_equity_usdt=account.current_equity_usdt,
        uta_basis_start_date=uta_basis_start_date(session, account) if session else None,
    )


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(session: SessionDep) -> list[AccountRead]:
    rows = list(session.exec(select(Account)).all())
    return [_to_read(r, session) for r in rows]


def _validate_bitget_activation(session: Session, account: Account, exchange: Exchange) -> None:
    if not account.enabled or account.is_simulated or exchange.name != "bitget":
        return
    others = list(session.exec(
        select(Account).where(
            Account.exchange_id == exchange.id,
            Account.id != account.id,
            Account.enabled == True,
            Account.is_simulated == False,
        ).execution_options(populate_existing=True)
    ).all())
    is_uta = account.account_type == AccountType.BITGET_UTA
    if not is_uta:
        others = [row for row in others if row.account_type == AccountType.BITGET_UTA]
        if not others:
            return

    def identity(row: Account) -> tuple[ExchangeConnectionState | None, dict]:
        state = session.exec(select(ExchangeConnectionState).where(
            ExchangeConnectionState.account_id == row.id
        )).first()
        details = json.loads(state.details_json or "{}") if state else {}
        if not details.get("uid") and row.account_type != AccountType.BITGET_UTA:
            client = None
            try:
                client = build_client_for_account(session, row)
                details = client.fetch_account_details()
            except Exception:
                raise HTTPException(status_code=409, detail=f"Cannot verify Bitget account #{row.id} UID; test or disable it first") from None
            finally:
                if client is not None:
                    client.close()
            if details.get("uid"):
                if state is None:
                    state = ExchangeConnectionState(account_id=row.id)
                state.details_json = json.dumps(details)
                session.add(state)
        return state, details

    state, details = identity(account)
    uid = details.get("uid")
    if not uid or (is_uta and (state is None or state.status != "connected" or details.get("blockers"))):
        raise HTTPException(status_code=409, detail="Test the Bitget connection successfully before enabling UTA")
    for other in others:
        _, other_details = identity(other)
        if not other_details.get("uid"):
            raise HTTPException(status_code=409, detail=f"Bitget account #{other.id} has an unknown UID; test or disable it first")
        if other_details["uid"] == uid:
            raise HTTPException(status_code=409, detail=f"Bitget account #{other.id} with the same UID is already enabled; disable it or use the migration script")


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_account(payload: AccountCreate, session: SessionDep) -> AccountRead:
    exchange = session.get(Exchange, payload.exchange_id)
    if exchange is None:
        raise HTTPException(status_code=404, detail="exchange not found")

    is_uta = payload.account_type == AccountType.BITGET_UTA
    if is_uta and (exchange.name != "bitget" or payload.is_simulated):
        raise HTTPException(status_code=400, detail="bitget_uta requires a real Bitget account")

    account = Account(
        exchange_id=payload.exchange_id,
        account_name=payload.account_name,
        account_type=payload.account_type,
        api_key_enc=encrypt_secret(payload.api_key) if payload.api_key else None,
        api_secret_enc=encrypt_secret(payload.api_secret) if payload.api_secret else None,
        passphrase_enc=encrypt_secret(payload.passphrase) if payload.passphrase else None,
        is_simulated=payload.is_simulated,
        enabled=False if is_uta else payload.enabled,
    )
    session.add(account)
    try:
        session.flush()
        _validate_bitget_activation(session, account, exchange)
    except Exception:
        session.rollback()
        raise
    session.commit()
    session.refresh(account)
    return _to_read(account, session)


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int, payload: AccountUpdate, session: SessionDep
) -> AccountRead:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    data = payload.model_dump(exclude_unset=True)
    was_enabled = account.enabled
    next_type = data.get("account_type", account.account_type)
    if next_type != account.account_type and AccountType.BITGET_UTA in (next_type, account.account_type):
        raise HTTPException(status_code=409, detail="Use the Bitget UTA migration script to change account mode")
    credentials_changed = bool(
        {"api_key", "api_secret", "passphrase"}.intersection(data)
    )
    if "api_key" in data:
        account.api_key_enc = encrypt_secret(data.pop("api_key"))
    if "api_secret" in data:
        account.api_secret_enc = encrypt_secret(data.pop("api_secret"))
    if "passphrase" in data:
        account.passphrase_enc = encrypt_secret(data.pop("passphrase"))

    for field, value in data.items():
        setattr(account, field, value)

    if credentials_changed:
        state = session.exec(
            select(ExchangeConnectionState).where(
                ExchangeConnectionState.account_id == account_id
            )
        ).first()
        if account.account_type == AccountType.BITGET_UTA:
            if state is not None:
                stored = json.loads(state.details_json or "{}")
                state.status = "unknown"
                state.last_test_at = None
                state.latency_ms = None
                state.message = None
                state.details_json = json.dumps({"owner_uid": stored.get("owner_uid") or stored.get("uid")})
                session.add(state)
            account.enabled = False
            account.current_equity_usdt = None
            for preview in session.exec(select(HistoryImportPreview).where(
                HistoryImportPreview.account_id == account_id, HistoryImportPreview.committed_at == None,
            )).all():
                session.delete(preview)
        elif state is not None:
            session.delete(state)

    session.add(account)
    try:
        # Flush before checking identities: SQLite serializes competing activations.
        session.flush()
        exchange = session.get(Exchange, account.exchange_id)
        if exchange is None:
            raise HTTPException(status_code=404, detail="exchange not found")
        if not was_enabled or credentials_changed:
            _validate_bitget_activation(session, account, exchange)
    except Exception:
        session.rollback()
        raise
    session.commit()
    session.refresh(account)
    return _to_read(account, session)


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_account(account_id: int, session: SessionDep) -> None:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    connection_state = session.exec(
        select(ExchangeConnectionState).where(
            ExchangeConnectionState.account_id == account_id
        )
    ).first()
    if connection_state is not None:
        session.delete(connection_state)
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
        unmapped_symbols=outcome.unmapped_symbols,
    )
