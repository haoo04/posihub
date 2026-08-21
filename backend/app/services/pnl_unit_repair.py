"""One-time repair for legacy inverse-position PnL units."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..db.models import (
    Account,
    AccountSnapshotDaily,
    AccountType,
    DataMigration,
    DataSource,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionSnapshotDaily,
)
from .pnl_calculator import settlement_coin_to_usdt

MIGRATION_KEY = "coin-pnl-usdt-v1"


@dataclass(slots=True)
class PnlRepairReport:
    already_applied: bool = False
    current_positions: int = 0
    position_snapshots: int = 0
    account_snapshots: int = 0
    current_delta_usdt: float = 0.0
    snapshot_delta_usdt: float = 0.0
    skipped_without_mark: int = 0
    skipped_with_order_children: int = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _has_children(session: Session, position_id: int) -> bool:
    if session.exec(
        select(PositionOrder.id)
        .where(PositionOrder.position_id == position_id)
        .limit(1)
    ).first() is not None:
        return True
    return session.exec(
        select(PositionCloseExecution.id)
        .where(PositionCloseExecution.position_id == position_id)
        .limit(1)
    ).first() is not None


def repair_coin_pnl_units(
    session: Session,
    *,
    dry_run: bool = True,
) -> PnlRepairReport:
    """Convert legacy coin PnL exactly once.

    The old rows without order children came directly from Bitget and were in
    settlement coin.  Rows with order children are already calculated by the
    local USDT formula and are explicitly excluded.  A DB migration marker
    makes a second ``--apply`` a no-op instead of multiplying values again.
    """

    marker = session.get(DataMigration, MIGRATION_KEY)
    if marker is not None:
        return PnlRepairReport(already_applied=True)

    report = PnlRepairReport()
    coin_account_ids = {
        int(account.id)
        for account in session.exec(
            select(Account).where(Account.account_type == AccountType.COIN_PERP)
        ).all()
        if account.id is not None
    }

    current_rows = list(
        session.exec(select(PositionCurrent)).all()
    )
    for row in current_rows:
        if row.account_id not in coin_account_ids or row.source != DataSource.API:
            continue
        if row.id is None or _has_children(session, row.id):
            continue
        old = float(row.unrealized_pnl or 0.0)
        mark = float(row.mark_price or 0.0)
        if mark <= 0:
            report.skipped_without_mark += 1
            continue
        converted = settlement_coin_to_usdt(old, mark)
        report.current_positions += 1
        report.current_delta_usdt += converted - old
        if not dry_run:
            row.unrealized_pnl = converted
            session.add(row)

    positions_with_children = {
        (row.account_id, row.canonical_symbol, row.side)
        for row in current_rows
        if row.account_id in coin_account_ids
        and row.id is not None
        and _has_children(session, row.id)
    }

    # Position snapshots contain the mark price, so convert them directly and
    # accumulate deltas for the duplicated account-level total below.
    snapshot_deltas: dict[tuple[object, int], float] = defaultdict(float)
    for row in session.exec(select(PositionSnapshotDaily)).all():
        if row.account_id not in coin_account_ids or row.source != DataSource.API:
            continue
        if (row.account_id, row.canonical_symbol, row.side) in positions_with_children:
            # A locally reconstructed order ledger is already USDT-native.
            report.skipped_with_order_children += 1
            continue
        old = float(row.unrealized_pnl or 0.0)
        mark = float(row.mark_price or 0.0)
        if mark <= 0:
            report.skipped_without_mark += 1
            continue
        converted = settlement_coin_to_usdt(old, mark)
        report.position_snapshots += 1
        delta = converted - old
        report.snapshot_delta_usdt += delta
        snapshot_deltas[(row.snapshot_date, row.account_id)] += delta
        if not dry_run:
            row.unrealized_pnl = converted
            session.add(row)

    # AccountSnapshotDaily stores the account total once per balance asset.
    # Adjust a single stable-coin row so a multi-asset account is not changed
    # multiple times.
    account_snapshot_rows = list(session.exec(select(AccountSnapshotDaily)).all())
    grouped: dict[tuple[object, int], list[AccountSnapshotDaily]] = defaultdict(list)
    for row in account_snapshot_rows:
        if row.account_id in coin_account_ids and row.source == DataSource.API:
            grouped[(row.snapshot_date, row.account_id)].append(row)
    for key, delta in snapshot_deltas.items():
        candidates = grouped.get(key, [])
        if not candidates:
            continue
        target = next(
            (row for row in candidates if row.asset.upper() == "USDT"),
            sorted(candidates, key=lambda row: (row.asset, row.id or 0))[0],
        )
        report.account_snapshots += 1
        if not dry_run:
            target.total_unrealized_pnl += delta
            session.add(target)

    if not dry_run:
        session.add(
            DataMigration(
                key=MIGRATION_KEY,
                details_json=json.dumps(asdict(report), ensure_ascii=False),
                applied_at=_utcnow(),
            )
        )
    return report
