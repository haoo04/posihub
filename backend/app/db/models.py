"""SQLModel ORM tables.

Mirrors the data model described in
`docs/trading-account-position-management-dev.md` (sections 6.1 - 6.5).

All monetary / quantity columns are stored as ``float`` for MVP simplicity;
upgrade to :class:`decimal.Decimal` when migrating to PostgreSQL.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Naive UTC datetime; SQLite stores naive datetimes by default."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Enums (stored as strings so they remain readable in SQLite)
# ---------------------------------------------------------------------------


class InstrumentType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    FUTURES = "futures"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    NET = "net"


class DataSource(str, Enum):
    API = "api"
    MANUAL = "manual"
    SIMULATED = "simulated"


class AccountType(str, Enum):
    SPOT = "spot"
    USDT_PERP = "usdt_perp"
    COIN_PERP = "coin_perp"
    FUTURES = "futures"
    FUNDING = "funding"
    SIMULATED = "simulated"


class ManualEntryType(str, Enum):
    BALANCE = "balance"
    POSITION = "position"
    SNAPSHOT = "snapshot"


class PositionOrderStatus(str, Enum):
    OPEN = "open"
    PARTIAL = "partial"
    CLOSED = "closed"


# ---------------------------------------------------------------------------
# Configuration tables
# ---------------------------------------------------------------------------


class Exchange(SQLModel, table=True):
    __tablename__ = "exchanges"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=64)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    exchange_id: int = Field(foreign_key="exchanges.id", index=True)
    account_name: str = Field(max_length=128)
    account_type: AccountType = Field(default=AccountType.SPOT)

    # Encrypted secrets (Fernet token strings); ``None`` for simulated accounts.
    api_key_enc: Optional[str] = Field(default=None)
    api_secret_enc: Optional[str] = Field(default=None)
    passphrase_enc: Optional[str] = Field(default=None)

    is_simulated: bool = Field(default=False)
    enabled: bool = Field(default=True)

    last_sync_at: Optional[datetime] = Field(default=None)
    last_sync_status: Optional[str] = Field(default=None, max_length=32)
    last_sync_error: Optional[str] = Field(default=None)
    consecutive_failures: int = Field(default=0)

    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Standardisation dictionary
# ---------------------------------------------------------------------------


class SymbolMapping(SQLModel, table=True):
    __tablename__ = "symbol_mappings"
    __table_args__ = (
        UniqueConstraint("exchange", "raw_symbol", name="uq_symbol_mapping_exchange_raw"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    exchange: str = Field(index=True, max_length=64)
    raw_symbol: str = Field(index=True, max_length=64)
    canonical_symbol: str = Field(index=True, max_length=64)
    base_asset: str = Field(max_length=32)
    quote_asset: str = Field(max_length=32)
    instrument_type: InstrumentType = Field(default=InstrumentType.SPOT)
    contract_size: float = Field(default=1.0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


class AccountBalanceCurrent(SQLModel, table=True):
    __tablename__ = "account_balances_current"
    __table_args__ = (
        UniqueConstraint("account_id", "asset", name="uq_balance_account_asset"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    asset: str = Field(max_length=32, index=True)
    equity: float = Field(default=0.0)
    available: float = Field(default=0.0)
    frozen: float = Field(default=0.0)
    updated_at: datetime = Field(default_factory=_utcnow)
    source: DataSource = Field(default=DataSource.API)


class PositionCurrent(SQLModel, table=True):
    __tablename__ = "positions_current"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "canonical_symbol",
            "side",
            name="uq_position_account_symbol_side",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    canonical_symbol: str = Field(max_length=64, index=True)
    side: PositionSide = Field(default=PositionSide.NET)
    qty: float = Field(default=0.0)
    entry_price: float = Field(default=0.0)
    mark_price: float = Field(default=0.0)
    unrealized_pnl: float = Field(default=0.0)
    leverage: float = Field(default=1.0)
    margin_mode: Optional[str] = Field(default=None, max_length=16)
    updated_at: datetime = Field(default_factory=_utcnow)
    source: DataSource = Field(default=DataSource.API)


class PositionOrder(SQLModel, table=True):
    """Order-level position tracking.

    Each order represents an individual entry into a position,
    allowing for order-level risk and PnL calculation.
    """
    __tablename__ = "position_orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    position_id: int = Field(foreign_key="positions_current.id", index=True)

    # Order source tracking
    source: DataSource = Field(default=DataSource.MANUAL)
    source_order_id: Optional[str] = Field(default=None, max_length=128)

    # Order status
    status: PositionOrderStatus = Field(default=PositionOrderStatus.OPEN)

    # Quantity tracking
    open_qty: float = Field(default=0.0)  # Original opening quantity
    remaining_qty: float = Field(default=0.0)  # Current remaining quantity

    # Price and risk parameters
    entry_price: float = Field(default=0.0)
    leverage: float = Field(default=1.0)
    mmr: Optional[float] = Field(default=None)  # Maintenance margin rate
    liquidation_price: Optional[float] = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Daily snapshots
# ---------------------------------------------------------------------------


class AccountSnapshotDaily(SQLModel, table=True):
    __tablename__ = "account_snapshots_daily"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "account_id",
            "asset",
            name="uq_account_snapshot_date_account_asset",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_date: date = Field(index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    asset: str = Field(default="USDT", max_length=32)
    total_equity: float = Field(default=0.0)
    total_unrealized_pnl: float = Field(default=0.0)
    total_available: float = Field(default=0.0)
    source: DataSource = Field(default=DataSource.API)
    created_at: datetime = Field(default_factory=_utcnow)


class PositionSnapshotDaily(SQLModel, table=True):
    __tablename__ = "position_snapshots_daily"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "account_id",
            "canonical_symbol",
            "side",
            name="uq_position_snapshot_date_account_symbol_side",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_date: date = Field(index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    canonical_symbol: str = Field(max_length=64, index=True)
    side: PositionSide = Field(default=PositionSide.NET)
    qty: float = Field(default=0.0)
    entry_price: float = Field(default=0.0)
    mark_price: float = Field(default=0.0)
    unrealized_pnl: float = Field(default=0.0)
    source: DataSource = Field(default=DataSource.API)
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Manual entry audit log
# ---------------------------------------------------------------------------


class ManualEntry(SQLModel, table=True):
    __tablename__ = "manual_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    entry_date: date = Field(index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    entry_type: ManualEntryType = Field(default=ManualEntryType.SNAPSHOT)
    payload_json: str = Field(default="{}")
    operator: str = Field(default="local", max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
