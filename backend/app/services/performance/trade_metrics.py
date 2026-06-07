"""Trade-level performance metrics from close executions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlmodel import Session, select

from ...db.models import Account, PositionCloseExecution, PositionCurrent
from .scope import PerformanceScope

PNL_EPSILON = 1e-8


@dataclass(slots=True)
class TradeMetrics:
    realized_pnl_total: float
    trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float
    avg_win: float
    avg_loss: float
    win_loss_ratio: float | None
    profit_factor: float | None
    largest_win: float
    largest_loss: float
    avg_trade_pnl: float
    max_win_streak: int
    max_loss_streak: int
    first_trade_at: datetime | None
    last_trade_at: datetime | None


def _range_datetimes(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    return start_dt, end_dt


def _streaks(pnls: list[float]) -> tuple[int, int]:
    """Return (max consecutive wins, max consecutive losses) in order."""

    max_win = max_loss = 0
    cur_win = cur_loss = 0
    for pnl in pnls:
        if pnl > PNL_EPSILON:
            cur_win += 1
            cur_loss = 0
            max_win = max(max_win, cur_win)
        elif pnl < -PNL_EPSILON:
            cur_loss += 1
            cur_win = 0
            max_loss = max(max_loss, cur_loss)
        else:
            cur_win = cur_loss = 0
    return max_win, max_loss


def compute_trade_metrics(
    session: Session,
    *,
    scope: PerformanceScope,
    start_date: date,
    end_date: date,
) -> TradeMetrics:
    """Aggregate close-execution stats for scoped accounts in the date range."""

    empty = TradeMetrics(
        realized_pnl_total=0.0,
        trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        win_rate=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        win_loss_ratio=None,
        profit_factor=None,
        largest_win=0.0,
        largest_loss=0.0,
        avg_trade_pnl=0.0,
        max_win_streak=0,
        max_loss_streak=0,
        first_trade_at=None,
        last_trade_at=None,
    )
    if not scope.account_ids:
        return empty

    start_dt, end_dt = _range_datetimes(start_date, end_date)
    rows = session.exec(
        select(PositionCloseExecution.realized_pnl, PositionCloseExecution.created_at)
        .join(PositionCurrent, PositionCurrent.id == PositionCloseExecution.position_id)
        .join(Account, Account.id == PositionCurrent.account_id)
        .where(PositionCurrent.account_id.in_(scope.account_ids))
        .where(PositionCloseExecution.created_at >= start_dt)
        .where(PositionCloseExecution.created_at <= end_dt)
        .order_by(PositionCloseExecution.created_at)
    ).all()

    if not rows:
        return empty

    pnls = [float(r[0] or 0.0) for r in rows]
    timestamps = [r[1] for r in rows if r[1] is not None]

    wins = [p for p in pnls if p > PNL_EPSILON]
    losses = [p for p in pnls if p < -PNL_EPSILON]
    breakeven_count = len(pnls) - len(wins) - len(losses)

    gross_profit = sum(wins)
    gross_loss = sum(losses)
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0

    win_loss_ratio: float | None = None
    if losses and avg_loss != 0.0:
        win_loss_ratio = avg_win / abs(avg_loss)

    profit_factor: float | None = None
    if losses and gross_loss != 0.0:
        profit_factor = gross_profit / abs(gross_loss)

    max_win_streak, max_loss_streak = _streaks(pnls)

    return TradeMetrics(
        realized_pnl_total=sum(pnls),
        trade_count=len(pnls),
        win_count=len(wins),
        loss_count=len(losses),
        breakeven_count=breakeven_count,
        win_rate=len(wins) / len(pnls),
        avg_win=avg_win,
        avg_loss=avg_loss,
        win_loss_ratio=win_loss_ratio,
        profit_factor=profit_factor,
        largest_win=max(pnls),
        largest_loss=min(pnls),
        avg_trade_pnl=sum(pnls) / len(pnls),
        max_win_streak=max_win_streak,
        max_loss_streak=max_loss_streak,
        first_trade_at=timestamps[0] if timestamps else None,
        last_trade_at=timestamps[-1] if timestamps else None,
    )
