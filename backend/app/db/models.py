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


class ExchangeConnectionState(SQLModel, table=True):
    """Latest read-only API connectivity test for an account."""

    __tablename__ = "exchange_connection_states"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_exchange_connection_state_account"),
    )

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    status: str = Field(default="unknown", max_length=24)
    last_test_at: datetime | None = Field(default=None)
    latency_ms: float | None = Field(default=None)
    message: str | None = Field(default=None, max_length=500)


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
    __table_args__ = (
        UniqueConstraint(
            "position_id",
            "source_order_id",
            name="uq_position_order_position_source_order",
        ),
    )

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
    margin: Optional[float] = Field(default=None)  # Margin amount in quote currency
    mmr: Optional[float] = Field(default=None)  # Maintenance margin rate
    liquidation_price: Optional[float] = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class PositionCloseExecution(SQLModel, table=True):
    """A single user/API initiated close action against a position.

    One execution may consume multiple ``PositionOrder`` rows under the
    FIFO matching rule and therefore yield multiple
    ``PositionOrderMatch`` rows.
    """

    __tablename__ = "position_close_executions"
    __table_args__ = (
        UniqueConstraint(
            "position_id",
            "source_order_id",
            name="uq_close_execution_position_source_order",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    position_id: int = Field(foreign_key="positions_current.id", index=True)

    close_qty: float = Field(default=0.0)
    close_price: float = Field(default=0.0)

    source: DataSource = Field(default=DataSource.MANUAL)
    source_order_id: Optional[str] = Field(default=None, max_length=128)

    realized_pnl: float = Field(default=0.0)

    created_at: datetime = Field(default_factory=_utcnow)


class PositionOrderMatch(SQLModel, table=True):
    """FIFO match record between an open ``PositionOrder`` leg and a
    ``PositionCloseExecution`` leg.

    Each row represents one slice of consumption: ``matched_qty`` units
    of the open leg were closed at ``close_price`` against ``open_price``,
    yielding ``realized_pnl`` for that slice.
    """

    __tablename__ = "position_order_matches"

    id: Optional[int] = Field(default=None, primary_key=True)
    open_order_id: int = Field(foreign_key="position_orders.id", index=True)
    close_order_id: int = Field(
        foreign_key="position_close_executions.id", index=True
    )

    matched_qty: float = Field(default=0.0)
    open_price: float = Field(default=0.0)
    close_price: float = Field(default=0.0)
    realized_pnl: float = Field(default=0.0)

    matched_at: datetime = Field(default_factory=_utcnow)


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


class DataMigration(SQLModel, table=True):
    """Idempotency ledger for one-time, operator-run data repairs."""

    __tablename__ = "data_migrations"

    key: str = Field(primary_key=True, max_length=128)
    details_json: str = Field(default="{}")
    applied_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# History import preview cache
# ---------------------------------------------------------------------------


class HistoryImportPreview(SQLModel, table=True):
    """Server-side cache for a history-import preview.

    The exchange is queried only during the preview step; the normalised
    orders are stored here so the subsequent ``commit`` is deterministic and
    re-classified against the live database without touching the network.
    """

    __tablename__ = "history_import_previews"

    id: str = Field(primary_key=True, max_length=64)  # UUID hex
    account_id: int = Field(foreign_key="accounts.id", index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime = Field(default_factory=_utcnow, index=True)
    committed_at: Optional[datetime] = Field(default=None)
