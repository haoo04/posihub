"""Equity-based performance metrics from daily account snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, select

from ...db.models import AccountBalanceCurrent, AccountSnapshotDaily
from ..aggregate.pnl_calculator import aggregate_daily_equity
from .scope import PerformanceScope

STABLE_ASSETS = frozenset({"USDT", "USDC", "USD"})


@dataclass(slots=True)
class EquityPoint:
    snapshot_date: date
    total_equity: float
    drawdown_pct: float


@dataclass(slots=True)
class EquityMetrics:
    equity_start: float
    equity_end: float
    equity_change: float
    equity_change_pct: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    annualized_return_pct: float
    calmar_ratio: float | None
    snapshot_days: int
    first_snapshot_date: date | None
    last_snapshot_date: date | None
    points: list[EquityPoint]


def annualized_return(total_return_pct: float, span_days: int) -> float:
    """Compound the period return to a 365-day horizon."""

    if span_days <= 0:
        return 0.0
    base = 1.0 + total_return_pct
    if base <= 0:
        return -1.0
    return base ** (365.0 / span_days) - 1.0


def drawdown_pct_series(equities: list[float]) -> list[float]:
    """Peak-to-trough drawdown percentage for each equity value."""

    if not equities:
        return []
    peak = equities[0]
    out: list[float] = []
    for eq in equities:
        peak = max(peak, eq)
        out.append((peak - eq) / peak if peak > 0 else 0.0)
    return out


def max_drawdown_pct(equities: list[float]) -> float:
    series = drawdown_pct_series(equities)
    return max(series) if series else 0.0


def _live_equity_usdt(session: Session, scope: PerformanceScope, asset: str) -> float:
    asset_upper = asset.upper()
    if asset_upper not in STABLE_ASSETS:
        return 0.0
    if not scope.account_ids:
        return 0.0

    rows = session.exec(
        select(AccountBalanceCurrent.equity).where(
            AccountBalanceCurrent.account_id.in_(scope.account_ids),
            AccountBalanceCurrent.asset == asset_upper,
        )
    ).all()
    return sum(float(v or 0.0) for v in rows)


def compute_equity_metrics(
    session: Session,
    *,
    scope: PerformanceScope,
    start_date: date,
    end_date: date,
    asset: str = "USDT",
) -> EquityMetrics:
    """Build equity curve and drawdown stats for the scoped accounts."""

    if not scope.account_ids:
        return EquityMetrics(
            equity_start=0.0,
            equity_end=0.0,
            equity_change=0.0,
            equity_change_pct=0.0,
            max_drawdown_pct=0.0,
            current_drawdown_pct=0.0,
            annualized_return_pct=0.0,
            calmar_ratio=None,
            snapshot_days=0,
            first_snapshot_date=None,
            last_snapshot_date=None,
            points=[],
        )

    asset_upper = asset.upper()
    rows = session.exec(
        select(
            AccountSnapshotDaily.snapshot_date,
            AccountSnapshotDaily.total_equity,
            AccountSnapshotDaily.total_unrealized_pnl,
        ).where(
            AccountSnapshotDaily.snapshot_date >= start_date,
            AccountSnapshotDaily.snapshot_date <= end_date,
            AccountSnapshotDaily.asset == asset_upper,
            AccountSnapshotDaily.account_id.in_(scope.account_ids),
        )
    ).all()

    aggregated = aggregate_daily_equity(
        [(r[0], float(r[1] or 0.0), float(r[2] or 0.0)) for r in rows]
    )
    equities = [p.total_equity for p in aggregated]
    dates = [p.snapshot_date for p in aggregated]

    live_equity = _live_equity_usdt(session, scope, asset_upper)
    if live_equity > 0 and (not dates or dates[-1] < end_date):
        if dates and dates[-1] == end_date:
            equities[-1] = live_equity
        else:
            dates.append(end_date)
            equities.append(live_equity)

    drawdowns = drawdown_pct_series(equities)
    points = [
        EquityPoint(
            snapshot_date=d,
            total_equity=eq,
            drawdown_pct=dd,
        )
        for d, eq, dd in zip(dates, equities, drawdowns, strict=True)
    ]

    equity_start = equities[0] if equities else 0.0
    equity_end = equities[-1] if equities else live_equity
    equity_change = equity_end - equity_start
    equity_change_pct = equity_change / equity_start if equity_start else 0.0

    mdd = max_drawdown_pct(equities)
    span_days = (dates[-1] - dates[0]).days if len(dates) >= 2 else 0
    ann_return = annualized_return(equity_change_pct, span_days)
    calmar: float | None = None
    if mdd > 0 and span_days > 0:
        calmar = ann_return / mdd

    return EquityMetrics(
        equity_start=equity_start,
        equity_end=equity_end,
        equity_change=equity_change,
        equity_change_pct=equity_change_pct,
        max_drawdown_pct=mdd,
        current_drawdown_pct=drawdowns[-1] if drawdowns else 0.0,
        annualized_return_pct=ann_return,
        calmar_ratio=calmar,
        snapshot_days=len(aggregated),
        first_snapshot_date=aggregated[0].snapshot_date if aggregated else None,
        last_snapshot_date=aggregated[-1].snapshot_date if aggregated else None,
        points=points,
    )
