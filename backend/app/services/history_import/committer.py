"""Transactional writer for a classified history import.

Re-runs classification + FIFO simulation against the live database (so the
commit is deterministic and never trusts a stale plan), then writes only the
``NEW`` records: open orders become ``PositionOrder`` rows and close orders go
through the shared :func:`position_order_close.fifo_close_position` so the same
match / execution / parent-refresh logic is reused.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from ...db.models import (
    DataSource,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
)
from ..position_order_close import fifo_close_position
from .classifier import load_local_state
from .simulator import simulate
from .types import DedupStatus, ImportAction, NormalizedHistoryOrder


class HistoryImportError(ValueError):
    """Raised when a commit cannot proceed (e.g. unresolved blockers)."""


@dataclass(slots=True)
class CommitResult:
    created_opens: int = 0
    created_closes: int = 0
    skipped: int = 0
    conflicts: int = 0
    orphans: int = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_or_create_position(
    session: Session,
    *,
    account_id: int,
    canonical_symbol: str,
    side: PositionSide,
) -> PositionCurrent:
    existing = session.exec(
        select(PositionCurrent)
        .where(PositionCurrent.account_id == account_id)
        .where(PositionCurrent.canonical_symbol == canonical_symbol)
        .where(PositionCurrent.side == side)
    ).first()
    if existing is not None:
        return existing

    position = PositionCurrent(
        account_id=account_id,
        canonical_symbol=canonical_symbol,
        side=side,
        qty=0.0,
        source=DataSource.API,
    )
    session.add(position)
    session.flush()
    return position


def commit_history_import(
    session: Session,
    *,
    account_id: int,
    orders: list[NormalizedHistoryOrder],
) -> CommitResult:
    """Write the ``NEW`` open/close records from ``orders`` for ``account_id``.

    The caller owns the transaction (commit / rollback). Raises
    :class:`HistoryImportError` if the simulation reports blockers.
    """

    local_state = load_local_state(session, account_id)
    preview = simulate(orders, local_state)
    if preview.blockers:
        raise HistoryImportError("; ".join(preview.blockers))

    status_by_id = {p.source_order_id: p.dedup_status for p in preview.orders}
    result = CommitResult()
    now = _utcnow()

    grouped: dict[tuple[str, str], list[NormalizedHistoryOrder]] = {}
    for order in orders:
        if order.canonical_symbol is None:
            continue
        grouped.setdefault(order.group_key, []).append(order)

    for group_orders in grouped.values():
        canonical = group_orders[0].canonical_symbol
        side = group_orders[0].side
        assert canonical is not None  # blockers already rejected None symbols

        position = _get_or_create_position(
            session,
            account_id=account_id,
            canonical_symbol=canonical,
            side=side,
        )

        for order in sorted(
            group_orders, key=lambda o: (o.created_at, o.source_order_id)
        ):
            status = status_by_id.get(order.source_order_id, DedupStatus.NEW)
            if status == DedupStatus.SKIP_EXISTS:
                result.skipped += 1
                continue
            if status == DedupStatus.CONFLICT:
                result.conflicts += 1
                continue
            if status == DedupStatus.ORPHAN_CLOSE:
                result.orphans += 1
                continue

            if order.action == ImportAction.OPEN:
                po = PositionOrder(
                    position_id=position.id,
                    source=DataSource.API,
                    source_order_id=order.source_order_id,
                    status=PositionOrderStatus.OPEN,
                    open_qty=order.qty,
                    remaining_qty=order.qty,
                    entry_price=order.price,
                    created_at=order.created_at,
                    updated_at=now,
                )
                session.add(po)
                session.flush()
                result.created_opens += 1
            else:
                fifo_close_position(
                    session,
                    position_id=position.id,
                    close_qty=order.qty,
                    close_price=order.price,
                    source=DataSource.API,
                    source_order_id=order.source_order_id,
                )
                result.created_closes += 1

    return result
