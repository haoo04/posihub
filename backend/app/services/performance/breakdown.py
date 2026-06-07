"""Dimensional breakdown + daily series for close-execution performance."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlmodel import Session, select

from ...db.models import (
    Account,
    Exchange,
    PositionCloseExecution,
    PositionCurrent,
)
from .scope import PerformanceScope

PNL_EPSILON = 1e-8

VALID_DIMENSIONS = frozenset({"symbol", "account", "side", "exchange"})


@dataclass(slots=True)
class BreakdownRow:
    key: str
    label: str
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float
    realized_pnl_total: float
    avg_pnl: float


@dataclass(slots=True)
class RealizedPoint:
    trade_date: date
    realized_pnl: float
    trade_count: int


@dataclass(slots=True)
class _Bucket:
    pnls: list[float] = field(default_factory=list)


def _range_datetimes(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    return datetime.combine(start_date, time.min), datetime.combine(end_date, time.max)


def _row_from_pnls(key: str, label: str, pnls: list[float]) -> BreakdownRow:
    wins = [p for p in pnls if p > PNL_EPSILON]
    losses = [p for p in pnls if p < -PNL_EPSILON]
    total = sum(pnls)
    count = len(pnls)
    return BreakdownRow(
        key=key,
        label=label,
        trade_count=count,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=len(wins) / count if count else 0.0,
        realized_pnl_total=total,
        avg_pnl=total / count if count else 0.0,
    )


def compute_breakdown(
    session: Session,
    *,
    scope: PerformanceScope,
    dimension: str,
    start_date: date,
    end_date: date,
) -> list[BreakdownRow]:
    """Group close-execution realized PnL by the requested dimension."""

    if dimension not in VALID_DIMENSIONS:
        raise ValueError(f"unsupported dimension: {dimension}")
    if not scope.account_ids:
        return []

    start_dt, end_dt = _range_datetimes(start_date, end_date)
    rows = session.exec(
        select(
            PositionCloseExecution.realized_pnl,
            PositionCurrent.canonical_symbol,
            PositionCurrent.side,
            PositionCurrent.account_id,
            Account.account_name,
            Account.exchange_id,
            Exchange.name,
        )
        .join(PositionCurrent, PositionCurrent.id == PositionCloseExecution.position_id)
        .join(Account, Account.id == PositionCurrent.account_id)
        .join(Exchange, Exchange.id == Account.exchange_id)
        .where(PositionCurrent.account_id.in_(scope.account_ids))
        .where(PositionCloseExecution.created_at >= start_dt)
        .where(PositionCloseExecution.created_at <= end_dt)
    ).all()

    buckets: dict[str, _Bucket] = defaultdict(_Bucket)
    labels: dict[str, str] = {}
    for pnl, symbol, side, account_id, account_name, exchange_id, exchange_name in rows:
        if dimension == "symbol":
            key = symbol or "?"
            label = key
        elif dimension == "side":
            key = side.value if hasattr(side, "value") else str(side)
            label = key
        elif dimension == "account":
            key = str(account_id)
            label = account_name or f"账户 {account_id}"
        else:  # exchange
            key = str(exchange_id)
            label = exchange_name or f"交易所 {exchange_id}"

        buckets[key].pnls.append(float(pnl or 0.0))
        labels.setdefault(key, label)

    result = [
        _row_from_pnls(key, labels[key], bucket.pnls)
        for key, bucket in buckets.items()
    ]
    result.sort(key=lambda r: r.realized_pnl_total, reverse=True)
    return result


def compute_realized_series(
    session: Session,
    *,
    scope: PerformanceScope,
    start_date: date,
    end_date: date,
) -> list[RealizedPoint]:
    """Daily realized PnL series over the requested window."""

    if not scope.account_ids:
        return []

    start_dt, end_dt = _range_datetimes(start_date, end_date)
    rows = session.exec(
        select(
            PositionCloseExecution.realized_pnl,
            PositionCloseExecution.created_at,
        )
        .join(PositionCurrent, PositionCurrent.id == PositionCloseExecution.position_id)
        .where(PositionCurrent.account_id.in_(scope.account_ids))
        .where(PositionCloseExecution.created_at >= start_dt)
        .where(PositionCloseExecution.created_at <= end_dt)
    ).all()

    daily: dict[date, list[float]] = defaultdict(list)
    for pnl, created_at in rows:
        if created_at is None:
            continue
        daily[created_at.date()].append(float(pnl or 0.0))

    return [
        RealizedPoint(
            trade_date=d,
            realized_pnl=sum(pnls),
            trade_count=len(pnls),
        )
        for d, pnls in sorted(daily.items())
    ]
