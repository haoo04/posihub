"""Tests for the per-account position-merge logic.

Two raw positions on the same exchange can legitimately map to the same
canonical symbol (for example after a whitelist update points an ambiguous
raw symbol at a unified key). ``PositionCurrent`` enforces uniqueness on
``(account_id, canonical_symbol, side)``, so the normalizer must collapse
those duplicates before persistence.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.db.models import DataSource, PositionCurrent, PositionSide
from app.services.normalize.normalizer import (
    NormalizedPosition,
    merge_positions,
    upsert_positions,
)


def _make(
    *,
    account_id: int = 1,
    canonical: str = "BTC-USDT-PERP",
    side: PositionSide = PositionSide.LONG,
    qty: float,
    entry: float,
    mark: float = 0.0,
    upnl: float = 0.0,
    leverage: float = 1.0,
    margin_mode: str | None = None,
    raw: str = "",
) -> NormalizedPosition:
    return NormalizedPosition(
        account_id=account_id,
        canonical_symbol=canonical,
        side=side,
        qty=qty,
        entry_price=entry,
        mark_price=mark,
        unrealized_pnl=upnl,
        leverage=leverage,
        margin_mode=margin_mode,
        source=DataSource.API,
        updated_at=datetime(2026, 1, 1),
        raw_symbol=raw,
    )


def test_merge_positions_passes_unique_items_through() -> None:
    items = [
        _make(canonical="BTC-USDT-PERP", side=PositionSide.LONG, qty=1, entry=30000),
        _make(canonical="ETH-USDT-PERP", side=PositionSide.LONG, qty=2, entry=2000),
    ]
    out = merge_positions(items)
    assert len(out) == 2
    assert out[0].canonical_symbol == "BTC-USDT-PERP"
    assert out[1].canonical_symbol == "ETH-USDT-PERP"


def test_merge_positions_combines_same_canonical_and_side() -> None:
    items = [
        _make(qty=1.0, entry=30_000.0, mark=31_000.0, upnl=1_000.0, leverage=5),
        _make(qty=3.0, entry=32_000.0, mark=31_000.0, upnl=-3_000.0, leverage=10),
    ]
    out = merge_positions(items)
    assert len(out) == 1

    merged = out[0]
    assert merged.qty == 4.0
    # qty-weighted entry: (1*30000 + 3*32000) / 4 == 31500
    assert merged.entry_price == 31_500.0
    assert merged.unrealized_pnl == -2_000.0
    # first non-zero leverage wins
    assert merged.leverage == 5


def test_merge_positions_keeps_long_and_short_separate() -> None:
    items = [
        _make(side=PositionSide.LONG, qty=1, entry=30_000),
        _make(side=PositionSide.SHORT, qty=1, entry=30_500),
    ]
    out = merge_positions(items)
    assert len(out) == 2
    sides = {p.side for p in out}
    assert sides == {PositionSide.LONG, PositionSide.SHORT}


def test_merge_positions_zero_total_qty_falls_back_to_first_nonzero_entry() -> None:
    items = [
        _make(qty=0.0, entry=0.0),
        _make(qty=0.0, entry=30_000.0, mark=30_500.0),
    ]
    out = merge_positions(items)
    assert len(out) == 1
    assert out[0].qty == 0.0
    assert out[0].entry_price == 30_000.0
    assert out[0].mark_price == 30_500.0


def test_upsert_positions_persists_one_row_per_canonical_side(
    in_memory_session: Session,
) -> None:
    items = [
        _make(qty=1.0, entry=30_000.0, raw="BTCUSDT"),
        _make(qty=3.0, entry=32_000.0, raw="BTC/USDT:USDT"),
    ]
    written = upsert_positions(in_memory_session, account_id=1, items=items)
    in_memory_session.commit()

    rows = list(
        in_memory_session.exec(
            select(PositionCurrent).where(PositionCurrent.account_id == 1)
        )
    )
    assert written == 1
    assert len(rows) == 1
    assert rows[0].qty == 4.0
    assert rows[0].entry_price == 31_500.0
