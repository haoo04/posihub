"""Account DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from ..db.models import AccountType
from .common import APIModel


class AccountCreate(APIModel):
    exchange_id: int
    account_name: str = Field(min_length=1, max_length=128)
    account_type: AccountType = AccountType.SPOT
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    is_simulated: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_credentials(self) -> "AccountCreate":
        if self.is_simulated:
            return self
        if not self.api_key or not self.api_secret:
            raise ValueError("api_key and api_secret are required for non-simulated accounts")
        return self


class AccountUpdate(APIModel):
    account_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    account_type: Optional[AccountType] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    enabled: Optional[bool] = None


class AccountRead(APIModel):
    id: int
    exchange_id: int
    account_name: str
    account_type: AccountType
    is_simulated: bool
    enabled: bool
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    consecutive_failures: int = 0
    created_at: datetime
    api_key_masked: Optional[str] = None


class AccountSyncStatus(APIModel):
    account_id: int
    success: bool
    message: str
    synced_at: datetime
    unmapped_symbols: list[str] = []
