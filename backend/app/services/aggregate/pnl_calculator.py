"""Time-series PnL calculation from daily snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class PnlPoint:
    snapshot_date: date
    total_equity: float
    total_unrealized_pnl: float


def aggregate_daily_equity(rows: Iterable[tuple[date, float, float]]) -> list[PnlPoint]:
    """Aggregate ``(snapshot_date, total_equity, total_unrealized_pnl)`` tuples.

    Multiple rows on the same date (e.g. across accounts) are summed.
    """

    bucket: dict[date, list[float]] = {}
    for snap_date, equity, upnl in rows:
        if snap_date not in bucket:
            bucket[snap_date] = [0.0, 0.0]
        bucket[snap_date][0] += float(equity or 0.0)
        bucket[snap_date][1] += float(upnl or 0.0)

    return [
        PnlPoint(snapshot_date=d, total_equity=v[0], total_unrealized_pnl=v[1])
        for d, v in sorted(bucket.items())
    ]


def parse_range(value: str) -> int:
    """Parse range strings like ``7d`` / ``30d`` / ``90d`` into days."""

    if not value:
        raise ValueError("range is required")
    text = value.strip().lower()
    if text.endswith("d") and text[:-1].isdigit():
        days = int(text[:-1])
        if days <= 0:
            raise ValueError("range must be positive")
        return days
    raise ValueError(f"unsupported range: {value}")
