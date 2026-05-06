"""Tests for PnL aggregation utilities."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.aggregate.pnl_calculator import aggregate_daily_equity, parse_range


def test_aggregate_daily_equity_sums_per_date() -> None:
    rows = [
        (date(2026, 1, 1), 100.0, 5.0),
        (date(2026, 1, 1), 50.0, -2.0),
        (date(2026, 1, 2), 200.0, 10.0),
    ]
    result = aggregate_daily_equity(rows)
    assert len(result) == 2
    assert result[0].snapshot_date == date(2026, 1, 1)
    assert result[0].total_equity == 150.0
    assert result[0].total_unrealized_pnl == 3.0
    assert result[1].snapshot_date == date(2026, 1, 2)
    assert result[1].total_equity == 200.0


def test_parse_range_valid() -> None:
    assert parse_range("7d") == 7
    assert parse_range("30d") == 30
    assert parse_range("90D") == 90


@pytest.mark.parametrize("bad", ["", "abc", "0d", "-1d", "30"])
def test_parse_range_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_range(bad)
