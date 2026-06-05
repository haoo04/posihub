"""FIFO simulation + dedup classification tests (no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models import PositionSide
from app.services.history_import.classifier import (
    LocalCloseExecution,
    LocalOpenOrder,
    LocalState,
)
from app.services.history_import.simulator import simulate
from app.services.history_import.types import (
    DedupStatus,
    ImportAction,
    NormalizedHistoryOrder,
)

_BASE = datetime(2026, 1, 1, 0, 0, 0)


def _order(
    sid: str,
    action: ImportAction,
    qty: float,
    price: float,
    *,
    minute: int = 0,
    side: PositionSide = PositionSide.LONG,
    canonical: str | None = "ETH-USDT-PERP",
) -> NormalizedHistoryOrder:
    return NormalizedHistoryOrder(
        source_order_id=sid,
        raw_symbol="ETH/USDT:USDT",
        canonical_symbol=canonical,
        side=side,
        action=action,
        qty=qty,
        price=price,
        created_at=_BASE + timedelta(minutes=minute),
    )


def test_open_then_full_close_matches_and_pnl() -> None:
    orders = [
        _order("o1", ImportAction.OPEN, 1.0, 2000.0, minute=0),
        _order("c1", ImportAction.CLOSE, 1.0, 2100.0, minute=1),
    ]
    result = simulate(orders, LocalState())
    assert result.summary.new_opens == 1
    assert result.summary.new_closes == 1
    close = next(o for o in result.orders if o.source_order_id == "c1")
    assert close.dedup_status == DedupStatus.NEW
    assert len(close.matches) == 1
    assert close.matches[0].realized_pnl == 100.0


def test_multi_open_single_close_is_fifo() -> None:
    orders = [
        _order("o1", ImportAction.OPEN, 0.4, 1000.0, minute=0),
        _order("o2", ImportAction.OPEN, 0.6, 2000.0, minute=1),
        _order("c1", ImportAction.CLOSE, 0.5, 3000.0, minute=2),
    ]
    result = simulate(orders, LocalState())
    close = next(o for o in result.orders if o.source_order_id == "c1")
    # Earliest leg (o1, 0.4) consumed first, then 0.1 from o2.
    refs = [m.open_source_order_id for m in close.matches]
    qtys = [m.matched_qty for m in close.matches]
    assert refs == ["o1", "o2"]
    assert abs(qtys[0] - 0.4) < 1e-9
    assert abs(qtys[1] - 0.1) < 1e-9


def test_orphan_close_when_no_inventory() -> None:
    orders = [_order("c1", ImportAction.CLOSE, 1.0, 2100.0, minute=0)]
    result = simulate(orders, LocalState())
    assert result.summary.orphans == 1
    close = result.orders[0]
    assert close.dedup_status == DedupStatus.ORPHAN_CLOSE


def test_skip_existing_open_and_close() -> None:
    local = LocalState(
        open_source_ids={"o1"},
        close_source_ids={"c1"},
        open_by_source_id={
            "o1": LocalOpenOrder(
                id=1,
                position_id=1,
                source_order_id="o1",
                canonical_symbol="ETH-USDT-PERP",
                side=PositionSide.LONG,
                entry_price=2000.0,
                remaining_qty=0.0,
                created_at=_BASE,
            )
        },
        close_by_source_id={
            "c1": LocalCloseExecution(source_order_id="c1", close_qty=1.0, close_price=2100.0)
        },
    )
    orders = [
        _order("o1", ImportAction.OPEN, 1.0, 2000.0, minute=0),
        _order("c1", ImportAction.CLOSE, 1.0, 2100.0, minute=1),
    ]
    result = simulate(orders, local)
    assert result.summary.skipped == 2
    assert result.summary.new_opens == 0
    assert result.summary.new_closes == 0


def test_conflict_on_price_mismatch() -> None:
    local = LocalState(
        open_source_ids={"o1"},
        open_by_source_id={
            "o1": LocalOpenOrder(
                id=1,
                position_id=1,
                source_order_id="o1",
                canonical_symbol="ETH-USDT-PERP",
                side=PositionSide.LONG,
                entry_price=2000.0,
                remaining_qty=1.0,
                created_at=_BASE,
            )
        },
    )
    orders = [_order("o1", ImportAction.OPEN, 1.0, 9999.0, minute=0)]
    result = simulate(orders, local)
    assert result.summary.conflicts == 1
    assert result.orders[0].dedup_status == DedupStatus.CONFLICT


def test_fill_time_ordering_prevents_orphan_close() -> None:
    """Close placed before open, but filled after open fill -> not orphan."""

    # Open: placed T+0, filled T+2. Close: placed T+1, filled T+3.
    orders = [
        _order("o1", ImportAction.OPEN, 1.0, 2000.0, minute=0),
        _order("c1", ImportAction.CLOSE, 1.0, 2100.0, minute=1),
    ]
    orders[0].created_at = _BASE + timedelta(minutes=2)
    orders[1].created_at = _BASE + timedelta(minutes=3)

    result = simulate(orders, LocalState())
    close = next(o for o in result.orders if o.source_order_id == "c1")
    assert close.dedup_status == DedupStatus.NEW
    assert result.summary.orphans == 0
    assert len(close.matches) == 1


def test_unmapped_symbol_is_blocker() -> None:
    orders = [_order("o1", ImportAction.OPEN, 1.0, 2000.0, canonical=None)]
    result = simulate(orders, LocalState())
    assert result.blockers
    assert "未映射" in result.blockers[0]
