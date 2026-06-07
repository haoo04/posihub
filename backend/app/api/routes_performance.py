"""Trading performance endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from ..schemas.performance import (
    BreakdownRowRead,
    DataCoverageRead,
    EquityPerformancePoint,
    EquityPerformanceSeries,
    PerformanceBreakdown,
    PerformanceScopeRead,
    PerformanceSummary,
    RealizedPnlPoint,
    RealizedPnlSeries,
    TradeRowRead,
    TradesPage,
)
from ..services.aggregate.pnl_calculator import parse_range
from ..services.performance.breakdown import (
    VALID_DIMENSIONS,
    compute_breakdown,
    compute_realized_series,
)
from ..services.performance.equity_metrics import compute_equity_metrics
from ..services.performance.live_exposure import compute_live_exposure
from ..services.performance.scope import parse_account_ids, resolve_performance_scope
from ..services.performance.trade_metrics import compute_trade_metrics
from ..services.performance.trades import SORTABLE_FIELDS, list_trades
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


def _resolve(
    session,
    *,
    range: str,
    account_ids: str | None,
    exchange_id: int | None,
    include_simulated: bool,
):
    """Shared parse + scope resolution; raises HTTPException(400) on bad input."""
    try:
        parsed_ids = parse_account_ids(account_ids)
        _, start_date, end_date = _period(range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scope = resolve_performance_scope(
        session,
        account_ids=parsed_ids,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
    return parsed_ids, scope, start_date, end_date


def _period(range: str) -> tuple[int, date, date]:
    days = parse_range(range)
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    return days, start_date, end_date


def _scope_read(scope, account_ids: list[int] | None) -> PerformanceScopeRead:
    return PerformanceScopeRead(
        account_ids=scope.account_ids,
        exchange_id=scope.exchange_id,
        include_simulated=scope.include_simulated,
        account_count=len(scope.account_ids),
    )


def _coverage(equity, trade) -> DataCoverageRead:
    return DataCoverageRead(
        snapshot_days=equity.snapshot_days,
        first_snapshot_date=equity.first_snapshot_date,
        last_snapshot_date=equity.last_snapshot_date,
        trade_count=trade.trade_count,
        first_trade_at=trade.first_trade_at,
        last_trade_at=trade.last_trade_at,
    )


@router.get("/summary", response_model=PerformanceSummary)
def get_performance_summary(
    session: SessionDep,
    range: str = Query("30d", description="Time window: 7d / 30d / 90d / Nd"),
    asset: str = Query("USDT"),
    account_ids: str | None = Query(
        default=None, description="Comma-separated account ids; omit for all"
    ),
    exchange_id: int | None = Query(default=None),
    include_simulated: bool = Query(default=False),
) -> PerformanceSummary:
    parsed_ids, scope, start_date, end_date = _resolve(
        session,
        range=range,
        account_ids=account_ids,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
    equity = compute_equity_metrics(
        session,
        scope=scope,
        start_date=start_date,
        end_date=end_date,
        asset=asset,
    )
    trade = compute_trade_metrics(
        session,
        scope=scope,
        start_date=start_date,
        end_date=end_date,
    )
    unrealized_pnl, open_position_count = compute_live_exposure(session, scope)

    return PerformanceSummary(
        range=range,
        asset=asset.upper(),
        period_start=start_date,
        period_end=end_date,
        scope=_scope_read(scope, parsed_ids),
        data_coverage=_coverage(equity, trade),
        equity_start=equity.equity_start,
        equity_end=equity.equity_end,
        equity_change=equity.equity_change,
        equity_change_pct=equity.equity_change_pct,
        max_drawdown_pct=equity.max_drawdown_pct,
        current_drawdown_pct=equity.current_drawdown_pct,
        annualized_return_pct=equity.annualized_return_pct,
        calmar_ratio=equity.calmar_ratio,
        realized_pnl_total=trade.realized_pnl_total,
        trade_count=trade.trade_count,
        win_count=trade.win_count,
        loss_count=trade.loss_count,
        breakeven_count=trade.breakeven_count,
        win_rate=trade.win_rate,
        avg_win=trade.avg_win,
        avg_loss=trade.avg_loss,
        win_loss_ratio=trade.win_loss_ratio,
        profit_factor=trade.profit_factor,
        largest_win=trade.largest_win,
        largest_loss=trade.largest_loss,
        avg_trade_pnl=trade.avg_trade_pnl,
        max_win_streak=trade.max_win_streak,
        max_loss_streak=trade.max_loss_streak,
        unrealized_pnl=unrealized_pnl,
        open_position_count=open_position_count,
    )


@router.get("/equity", response_model=EquityPerformanceSeries)
def get_performance_equity(
    session: SessionDep,
    range: str = Query("30d", description="Time window: 7d / 30d / 90d / Nd"),
    asset: str = Query("USDT"),
    account_ids: str | None = Query(
        default=None, description="Comma-separated account ids; omit for all"
    ),
    exchange_id: int | None = Query(default=None),
    include_simulated: bool = Query(default=False),
) -> EquityPerformanceSeries:
    parsed_ids, scope, start_date, end_date = _resolve(
        session,
        range=range,
        account_ids=account_ids,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
    equity = compute_equity_metrics(
        session,
        scope=scope,
        start_date=start_date,
        end_date=end_date,
        asset=asset,
    )
    trade = compute_trade_metrics(
        session,
        scope=scope,
        start_date=start_date,
        end_date=end_date,
    )

    return EquityPerformanceSeries(
        range=range,
        asset=asset.upper(),
        period_start=start_date,
        period_end=end_date,
        scope=_scope_read(scope, parsed_ids),
        points=[
            EquityPerformancePoint(
                snapshot_date=p.snapshot_date,
                total_equity=p.total_equity,
                drawdown_pct=p.drawdown_pct,
            )
            for p in equity.points
        ],
        data_coverage=_coverage(equity, trade),
    )


@router.get("/breakdown", response_model=PerformanceBreakdown)
def get_performance_breakdown(
    session: SessionDep,
    dimension: str = Query("symbol", description="symbol|account|side|exchange"),
    range: str = Query("30d", description="Time window: 7d / 30d / 90d / Nd"),
    asset: str = Query("USDT"),
    account_ids: str | None = Query(default=None),
    exchange_id: int | None = Query(default=None),
    include_simulated: bool = Query(default=False),
) -> PerformanceBreakdown:
    if dimension not in VALID_DIMENSIONS:
        raise HTTPException(
            status_code=400, detail=f"unsupported dimension: {dimension}"
        )
    parsed_ids, scope, start_date, end_date = _resolve(
        session,
        range=range,
        account_ids=account_ids,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
    rows = compute_breakdown(
        session,
        scope=scope,
        dimension=dimension,
        start_date=start_date,
        end_date=end_date,
    )
    return PerformanceBreakdown(
        range=range,
        asset=asset.upper(),
        dimension=dimension,
        period_start=start_date,
        period_end=end_date,
        scope=_scope_read(scope, parsed_ids),
        rows=[
            BreakdownRowRead(
                key=r.key,
                label=r.label,
                trade_count=r.trade_count,
                win_count=r.win_count,
                loss_count=r.loss_count,
                win_rate=r.win_rate,
                realized_pnl_total=r.realized_pnl_total,
                avg_pnl=r.avg_pnl,
            )
            for r in rows
        ],
    )


@router.get("/realized", response_model=RealizedPnlSeries)
def get_performance_realized(
    session: SessionDep,
    range: str = Query("30d", description="Time window: 7d / 30d / 90d / Nd"),
    asset: str = Query("USDT"),
    account_ids: str | None = Query(default=None),
    exchange_id: int | None = Query(default=None),
    include_simulated: bool = Query(default=False),
) -> RealizedPnlSeries:
    parsed_ids, scope, start_date, end_date = _resolve(
        session,
        range=range,
        account_ids=account_ids,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
    points = compute_realized_series(
        session,
        scope=scope,
        start_date=start_date,
        end_date=end_date,
    )
    return RealizedPnlSeries(
        range=range,
        asset=asset.upper(),
        period_start=start_date,
        period_end=end_date,
        scope=_scope_read(scope, parsed_ids),
        points=[
            RealizedPnlPoint(
                trade_date=p.trade_date,
                realized_pnl=p.realized_pnl,
                trade_count=p.trade_count,
            )
            for p in points
        ],
    )


@router.get("/trades", response_model=TradesPage)
def get_performance_trades(
    session: SessionDep,
    range: str = Query("30d", description="Time window: 7d / 30d / 90d / Nd"),
    asset: str = Query("USDT"),
    account_ids: str | None = Query(default=None),
    exchange_id: int | None = Query(default=None),
    include_simulated: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    sort_field: str = Query(default="closed_at"),
    sort_desc: bool = Query(default=True),
) -> TradesPage:
    if sort_field not in SORTABLE_FIELDS:
        raise HTTPException(
            status_code=400, detail=f"unsupported sort_field: {sort_field}"
        )
    parsed_ids, scope, start_date, end_date = _resolve(
        session,
        range=range,
        account_ids=account_ids,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
    result = list_trades(
        session,
        scope=scope,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_desc=sort_desc,
    )
    return TradesPage(
        range=range,
        asset=asset.upper(),
        period_start=start_date,
        period_end=end_date,
        scope=_scope_read(scope, parsed_ids),
        items=[
            TradeRowRead(
                execution_id=t.execution_id,
                account_id=t.account_id,
                account_name=t.account_name,
                canonical_symbol=t.canonical_symbol,
                side=t.side,
                close_qty=t.close_qty,
                close_price=t.close_price,
                realized_pnl=t.realized_pnl,
                closed_at=t.closed_at,
                hold_duration_hours=t.hold_duration_hours,
                source=t.source,
            )
            for t in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )
