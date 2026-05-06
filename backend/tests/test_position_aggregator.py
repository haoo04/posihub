"""Tests for position aggregation across accounts."""

from __future__ import annotations

from app.db.models import PositionSide
from app.services.aggregate.position_aggregator import (
    PositionInput,
    aggregate_positions,
)


def _make(
    account_id: int,
    symbol: str,
    side: PositionSide,
    qty: float,
    entry: float,
    mark: float = 0.0,
    upnl: float = 0.0,
) -> PositionInput:
    return PositionInput(
        account_id=account_id,
        canonical_symbol=symbol,
        side=side,
        qty=qty,
        entry_price=entry,
        mark_price=mark,
        unrealized_pnl=upnl,
    )


def test_aggregate_same_side_weighted_average() -> None:
    inputs = [
        _make(1, "BTC-USDT-PERP", PositionSide.LONG, 1.0, 30000.0, 31000.0, 1000.0),
        _make(2, "BTC-USDT-PERP", PositionSide.LONG, 3.0, 32000.0, 31000.0, -3000.0),
    ]
    result = aggregate_positions(inputs)
    assert len(result) == 1

    merged = result[0]
    assert merged.canonical_symbol == "BTC-USDT-PERP"
    assert merged.side == PositionSide.LONG
    assert merged.qty == 4.0
    # weighted: (1*30000 + 3*32000)/4 == 31500
    assert merged.avg_entry_price == 31500.0
    assert merged.unrealized_pnl == -2000.0
    assert merged.accounts == [1, 2]


def test_aggregate_offsetting_long_short() -> None:
    inputs = [
        _make(1, "ETH-USDT-PERP", PositionSide.LONG, 5.0, 2000.0, 2100.0, 500.0),
        _make(2, "ETH-USDT-PERP", PositionSide.SHORT, 2.0, 2050.0, 2100.0, -100.0),
    ]
    result = aggregate_positions(inputs)
    assert len(result) == 1
    merged = result[0]
    assert merged.side == PositionSide.LONG
    assert merged.qty == 3.0
    assert merged.avg_entry_price == 2000.0  # surviving long side weighted avg
    assert merged.unrealized_pnl == 400.0


def test_aggregate_perfect_hedge_drops_symbol() -> None:
    inputs = [
        _make(1, "BTC-USDT-PERP", PositionSide.LONG, 2.0, 30000.0),
        _make(2, "BTC-USDT-PERP", PositionSide.SHORT, 2.0, 29000.0),
    ]
    assert aggregate_positions(inputs) == []


def test_aggregate_skips_zero_qty() -> None:
    inputs = [_make(1, "BTC-USDT-PERP", PositionSide.LONG, 0.0, 30000.0)]
    assert aggregate_positions(inputs) == []
