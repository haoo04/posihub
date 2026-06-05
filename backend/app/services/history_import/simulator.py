"""Preview-time FIFO simulation (no DB writes).

Mirrors the chronological FIFO that the committer applies via
``position_order_close.fifo_close_position``: open events add inventory legs,
close events consume the earliest remaining legs first. Only ``NEW`` records
mutate state; ``skip_exists`` records are already reflected in the seed legs,
and ``conflict`` / ``orphan_close`` records are excluded from writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...db.models import PositionSide
from .classifier import LocalState
from .types import (
    PRICE_EPSILON,
    QTY_EPSILON,
    ClosedPositionSummary,
    DedupStatus,
    ImportAction,
    ImportPreviewResult,
    ImportSummary,
    NormalizedHistoryOrder,
    OrderPreview,
    PlannedMatch,
)


@dataclass(slots=True)
class _Leg:
    source_order_id: Optional[str]
    local_order_id: Optional[int]
    entry_price: float
    remaining_qty: float
    created_at: datetime


def _realized_pnl(
    side: PositionSide, open_price: float, close_price: float, qty: float
) -> float:
    if side == PositionSide.LONG:
        return (close_price - open_price) * qty
    if side == PositionSide.SHORT:
        return (open_price - close_price) * qty
    return 0.0


def _fifo_consume(
    legs: list[_Leg],
    *,
    side: PositionSide,
    close_qty: float,
    close_price: float,
) -> tuple[list[PlannedMatch], float]:
    """Consume ``close_qty`` from ``legs`` (mutating them) FIFO.

    Returns the planned matches and the quantity left unmatched (``> 0``
    means the close is an orphan). Legs are only mutated when the full
    quantity can be covered, matching ``fifo_close_position`` semantics.
    """

    available = sum(leg.remaining_qty for leg in legs)
    if close_qty - available > QTY_EPSILON:
        return [], close_qty - available

    # Consume earliest-opened legs first, matching the DB-side ordering in
    # ``fifo_close_position`` (``created_at`` asc) so preview equals commit.
    legs.sort(key=lambda leg: leg.created_at)

    matches: list[PlannedMatch] = []
    remaining = close_qty
    for leg in legs:
        if remaining <= QTY_EPSILON:
            break
        if leg.remaining_qty <= QTY_EPSILON:
            continue
        consume = min(leg.remaining_qty, remaining)
        pnl = _realized_pnl(side, leg.entry_price, close_price, consume)
        matches.append(
            PlannedMatch(
                open_source_order_id=leg.source_order_id,
                open_local_order_id=leg.local_order_id,
                matched_qty=consume,
                open_price=leg.entry_price,
                close_price=close_price,
                realized_pnl=pnl,
            )
        )
        leg.remaining_qty -= consume
        remaining -= consume

    return matches, max(remaining, 0.0)


def _classify_open(
    order: NormalizedHistoryOrder, local_state: LocalState
) -> DedupStatus:
    sid = order.source_order_id
    if sid not in local_state.open_source_ids:
        return DedupStatus.NEW
    existing = local_state.open_by_source_id.get(sid)
    if existing is None:
        return DedupStatus.SKIP_EXISTS
    if (
        abs(existing.remaining_qty - order.qty) > QTY_EPSILON
        and abs(existing.entry_price - order.price) > PRICE_EPSILON
    ):
        # Both quantity and price diverge -> genuine conflict.
        return DedupStatus.CONFLICT
    if abs(existing.entry_price - order.price) > PRICE_EPSILON:
        return DedupStatus.CONFLICT
    return DedupStatus.SKIP_EXISTS


def _classify_close(
    order: NormalizedHistoryOrder, local_state: LocalState
) -> DedupStatus:
    sid = order.source_order_id
    if sid not in local_state.close_source_ids:
        return DedupStatus.NEW
    existing = local_state.close_by_source_id.get(sid)
    if existing is None:
        return DedupStatus.SKIP_EXISTS
    if (
        abs(existing.close_qty - order.qty) > QTY_EPSILON
        or abs(existing.close_price - order.price) > PRICE_EPSILON
    ):
        return DedupStatus.CONFLICT
    return DedupStatus.SKIP_EXISTS


def simulate(
    orders: list[NormalizedHistoryOrder],
    local_state: LocalState,
    *,
    closed_positions: Optional[list[ClosedPositionSummary]] = None,
) -> ImportPreviewResult:
    """Classify and FIFO-simulate ``orders`` against existing local state."""

    result = ImportPreviewResult(closed_positions=closed_positions or [])
    summary = ImportSummary(total_fetched=len(orders))

    # Group orders by (canonical_symbol|raw_symbol, side).
    grouped: dict[tuple[str, str], list[NormalizedHistoryOrder]] = {}
    for order in orders:
        grouped.setdefault(order.group_key, []).append(order)

    previews: list[OrderPreview] = []
    unmapped_symbols: set[str] = set()

    for key, group_orders in grouped.items():
        canonical = group_orders[0].canonical_symbol
        side = group_orders[0].side

        legs: list[_Leg] = []
        for seed in local_state.seed_legs_by_group.get(key, []):
            legs.append(
                _Leg(
                    source_order_id=seed.source_order_id,
                    local_order_id=seed.id,
                    entry_price=seed.entry_price,
                    remaining_qty=seed.remaining_qty,
                    created_at=seed.created_at,
                )
            )

        ordered = sorted(group_orders, key=lambda o: (o.created_at, o.source_order_id))
        for order in ordered:
            preview = OrderPreview(
                source_order_id=order.source_order_id,
                raw_symbol=order.raw_symbol,
                canonical_symbol=order.canonical_symbol,
                side=order.side.value,
                action=order.action.value,
                qty=order.qty,
                price=order.price,
                created_at=order.created_at,
                dedup_status=DedupStatus.NEW,
                realized_pnl=order.realized_pnl,
            )

            if order.canonical_symbol is None:
                unmapped_symbols.add(order.raw_symbol)

            if order.action == ImportAction.OPEN:
                status = _classify_open(order, local_state)
                preview.dedup_status = status
                if status == DedupStatus.NEW:
                    legs.append(
                        _Leg(
                            source_order_id=order.source_order_id,
                            local_order_id=None,
                            entry_price=order.price,
                            remaining_qty=order.qty,
                            created_at=order.created_at,
                        )
                    )
                    summary.new_opens += 1
                elif status == DedupStatus.CONFLICT:
                    summary.conflicts += 1
                    preview.note = "本地已存在同订单号但数量/价格不一致"
                else:
                    summary.skipped += 1
            else:  # CLOSE
                status = _classify_close(order, local_state)
                if status == DedupStatus.SKIP_EXISTS:
                    preview.dedup_status = status
                    summary.skipped += 1
                elif status == DedupStatus.CONFLICT:
                    preview.dedup_status = status
                    summary.conflicts += 1
                    preview.note = "本地已存在同平仓订单号但数量/价格不一致"
                else:
                    matches, unmatched = _fifo_consume(
                        legs,
                        side=side,
                        close_qty=order.qty,
                        close_price=order.price,
                    )
                    if unmatched > QTY_EPSILON:
                        preview.dedup_status = DedupStatus.ORPHAN_CLOSE
                        preview.note = f"缺少可平仓的开仓腿（缺口 {unmatched:g}）"
                        summary.orphans += 1
                    else:
                        preview.dedup_status = DedupStatus.NEW
                        preview.matches = matches
                        summary.new_closes += 1

            previews.append(preview)

    previews.sort(key=lambda p: (p.created_at, p.source_order_id))
    result.orders = previews
    result.summary = summary

    if unmapped_symbols:
        result.blockers.append(
            "存在未映射的交易对，请先在符号映射中补全：" + ", ".join(sorted(unmapped_symbols))
        )

    return result
