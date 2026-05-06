"""Daily snapshot writer.

Persists a row per account into ``account_snapshots_daily`` and per position
into ``position_snapshots_daily``. Snapshot date is the local date according
to the configured timezone.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlmodel import Session, select

from ..core.config import get_settings
from ..core.logging import get_logger
from ..db.models import (
    Account,
    AccountBalanceCurrent,
    AccountSnapshotDaily,
    DataSource,
    PositionCurrent,
    PositionSnapshotDaily,
)
from ..db.session import session_scope

_logger = get_logger(__name__)


@dataclass(slots=True)
class SnapshotOutcome:
    snapshot_date: date
    accounts_written: int
    positions_written: int
    balances_aggregated: int


def _today_local() -> date:
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    return datetime.now(tz).date()


def write_daily_snapshots(snapshot_date: date | None = None) -> SnapshotOutcome:
    """Write daily snapshots for all accounts (idempotent per date)."""

    snap_date = snapshot_date or _today_local()
    accounts_written = 0
    positions_written = 0
    balances_aggregated = 0

    with session_scope() as session:
        # account-level snapshots: aggregate balance equity per account/asset
        balance_rows = list(session.exec(select(AccountBalanceCurrent)).all())
        positions_rows = list(session.exec(select(PositionCurrent)).all())
        accounts = {a.id: a for a in session.exec(select(Account)).all()}

        # group balances by (account_id, asset)
        agg: dict[tuple[int, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for row in balance_rows:
            key = (row.account_id, row.asset)
            agg[key][0] += float(row.equity or 0.0)
            agg[key][1] += float(row.available or 0.0)
        balances_aggregated = len(agg)

        # also track per-account total unrealized pnl from positions
        pnl_per_account: dict[int, float] = defaultdict(float)
        for pos in positions_rows:
            pnl_per_account[pos.account_id] += float(pos.unrealized_pnl or 0.0)

        # delete any existing snapshots for that date (idempotent)
        session.exec(  # type: ignore[call-arg]
            delete(AccountSnapshotDaily).where(
                AccountSnapshotDaily.snapshot_date == snap_date
            )
        )
        session.exec(  # type: ignore[call-arg]
            delete(PositionSnapshotDaily).where(
                PositionSnapshotDaily.snapshot_date == snap_date
            )
        )

        for (account_id, asset), (equity, available) in agg.items():
            account = accounts.get(account_id)
            source = (
                DataSource.SIMULATED
                if account and account.is_simulated
                else DataSource.API
            )
            session.add(
                AccountSnapshotDaily(
                    snapshot_date=snap_date,
                    account_id=account_id,
                    asset=asset,
                    total_equity=equity,
                    total_unrealized_pnl=pnl_per_account.get(account_id, 0.0),
                    total_available=available,
                    source=source,
                )
            )
            accounts_written += 1

        for pos in positions_rows:
            account = accounts.get(pos.account_id)
            source = (
                DataSource.SIMULATED
                if account and account.is_simulated
                else DataSource.API
            )
            session.add(
                PositionSnapshotDaily(
                    snapshot_date=snap_date,
                    account_id=pos.account_id,
                    canonical_symbol=pos.canonical_symbol,
                    side=pos.side,
                    qty=pos.qty,
                    entry_price=pos.entry_price,
                    mark_price=pos.mark_price,
                    unrealized_pnl=pos.unrealized_pnl,
                    source=source,
                )
            )
            positions_written += 1

    _logger.info(
        "snapshot %s: accounts=%d positions=%d",
        snap_date,
        accounts_written,
        positions_written,
    )
    return SnapshotOutcome(
        snapshot_date=snap_date,
        accounts_written=accounts_written,
        positions_written=positions_written,
        balances_aggregated=balances_aggregated,
    )


def write_account_snapshot(
    session: Session,
    *,
    account_id: int,
    snapshot_date: date,
    asset: str,
    total_equity: float,
    total_unrealized_pnl: float,
    total_available: float,
    source: DataSource,
) -> AccountSnapshotDaily:
    """Insert/replace a single account snapshot row (used by manual entries)."""

    session.exec(  # type: ignore[call-arg]
        delete(AccountSnapshotDaily).where(
            AccountSnapshotDaily.snapshot_date == snapshot_date,
            AccountSnapshotDaily.account_id == account_id,
            AccountSnapshotDaily.asset == asset,
        )
    )
    row = AccountSnapshotDaily(
        snapshot_date=snapshot_date,
        account_id=account_id,
        asset=asset,
        total_equity=total_equity,
        total_unrealized_pnl=total_unrealized_pnl,
        total_available=total_available,
        source=source,
    )
    session.add(row)
    return row
