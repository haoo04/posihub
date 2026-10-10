"""Paginated close-execution detail list with hold duration."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import and_, case, func
from sqlmodel import Session, select

from ...core.logging import get_logger
from ...db.models import (
    Account,
    AccountType,
    DataSource,
    Exchange,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionOrderMatch,
    PositionSide,
)
from ..pnl_calculator import quantity_context
from .scope import PerformanceScope

SORTABLE_FIELDS = frozenset({"closed_at", "realized_pnl", "close_qty"})
_logger = get_logger(__name__)


@dataclass(slots=True)
class TradeRow:
    execution_id: int
    account_id: int
    account_name: str
    canonical_symbol: str
    side: PositionSide
    close_qty: float | None
    close_price: float
    realized_pnl: float
    closed_at: datetime | None
    hold_duration_hours: float | None
    source: DataSource
    quantity_mode: str = "base"
    quantity_unit: str = ""
    quantity_warning: str | None = None


@dataclass(slots=True)
class TradesResult:
    items: list[TradeRow]
    total: int
    page: int
    page_size: int


def _range_datetimes(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    return datetime.combine(start_date, time.min), datetime.combine(end_date, time.max)


def _hold_durations_hours(
    session: Session, execution_ids: list[int]
) -> dict[int, float]:
    """Weighted-average hold duration (hours) per close execution.

    Duration of each consumed open leg = ``execution.created_at -
    open_order.created_at``, weighted by ``matched_qty``.
    """

    if not execution_ids:
        return {}

    rows = session.exec(
        select(
            PositionOrderMatch.close_order_id,
            PositionOrderMatch.matched_qty,
            PositionOrder.created_at,
            PositionCloseExecution.created_at,
            PositionOrderMatch.open_price,
            Account.account_type,
            Exchange.name,
            PositionCurrent.canonical_symbol,
        )
        .join(PositionOrder, PositionOrder.id == PositionOrderMatch.open_order_id)
        .join(
            PositionCloseExecution,
            PositionCloseExecution.id == PositionOrderMatch.close_order_id,
        )
        .join(PositionCurrent, PositionCurrent.id == PositionCloseExecution.position_id)
        .join(Account, Account.id == PositionCurrent.account_id)
        .join(Exchange, Exchange.id == Account.exchange_id)
        .where(PositionOrderMatch.close_order_id.in_(execution_ids))
    ).all()

    weighted: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for (
        close_id,
        matched_qty,
        open_at,
        close_at,
        open_price,
        account_type,
        exchange,
        symbol,
    ) in rows:
        if open_at is None or close_at is None:
            continue
        qty = float(matched_qty or 0.0)
        if quantity_context(exchange, account_type, symbol)["quantity_mode"] == "quote_contract":
            qty *= open_price
        if qty <= 0:
            continue
        hours = (close_at - open_at).total_seconds() / 3600.0
        bucket = weighted[int(close_id)]
        bucket[0] += hours * qty
        bucket[1] += qty

    return {
        cid: (acc[0] / acc[1])
        for cid, acc in weighted.items()
        if acc[1] > 0
    }


def list_trades(
    session: Session,
    *,
    scope: PerformanceScope,
    start_date: date,
    end_date: date,
    page: int = 1,
    page_size: int = 50,
    sort_field: str = "closed_at",
    sort_desc: bool = True,
) -> TradesResult:
    """Return a paginated page of close executions for scoped accounts."""

    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    if sort_field not in SORTABLE_FIELDS:
        sort_field = "closed_at"

    if not scope.account_ids:
        return TradesResult(items=[], total=0, page=page, page_size=page_size)

    start_dt, end_dt = _range_datetimes(start_date, end_date)

    base_filters = (
        PositionCurrent.account_id.in_(scope.account_ids),
        PositionCloseExecution.created_at >= start_dt,
        PositionCloseExecution.created_at <= end_dt,
    )

    total = session.exec(
        select(func.count())
        .select_from(PositionCloseExecution)
        .join(PositionCurrent, PositionCurrent.id == PositionCloseExecution.position_id)
        .where(*base_filters)
    ).one()
    total = int(total or 0)

    quote_totals = (
        select(
            PositionOrderMatch.close_order_id.label("close_id"),
            func.sum(PositionOrderMatch.matched_qty * PositionOrderMatch.open_price).label(
                "quote_qty"
            ),
            func.sum(func.max(PositionOrderMatch.open_price * 1e-8, 1e-9)).label("tolerance"),
        )
        .group_by(PositionOrderMatch.close_order_id)
        .subquery()
    )
    quote_qty = case(
        (
            and_(
                func.round(quote_totals.c.quote_qty) != 0,
                func.abs(quote_totals.c.quote_qty - func.round(quote_totals.c.quote_qty))
                <= quote_totals.c.tolerance + 1e-12,
            ),
            func.round(quote_totals.c.quote_qty),
        ),
        else_=quote_totals.c.quote_qty,
    )
    external_qty = case(
        (
            and_(
                func.lower(Exchange.name) == "bybit",
                Account.account_type == AccountType.COIN_PERP,
                func.upper(PositionCurrent.canonical_symbol).like("%-USD-PERP"),
            ),
            quote_qty,
        ),
        else_=PositionCloseExecution.close_qty,
    )
    sort_column = {
        "closed_at": PositionCloseExecution.created_at,
        "realized_pnl": PositionCloseExecution.realized_pnl,
        "close_qty": external_qty,
    }[sort_field]
    order_by = sort_column.desc() if sort_desc else sort_column.asc()

    rows = session.exec(
        select(
            PositionCloseExecution.id,
            external_qty,
            PositionCloseExecution.close_price,
            PositionCloseExecution.realized_pnl,
            PositionCloseExecution.created_at,
            PositionCloseExecution.source,
            PositionCurrent.account_id,
            PositionCurrent.canonical_symbol,
            PositionCurrent.side,
            Account.account_name,
            Account.account_type,
            Exchange.name,
        )
        .join(PositionCurrent, PositionCurrent.id == PositionCloseExecution.position_id)
        .join(Account, Account.id == PositionCurrent.account_id)
        .join(Exchange, Exchange.id == Account.exchange_id)
        .outerjoin(quote_totals, quote_totals.c.close_id == PositionCloseExecution.id)
        .where(*base_filters)
        .order_by(sort_column.is_(None), order_by, PositionCloseExecution.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    execution_ids = [int(r[0]) for r in rows]
    hold_map = _hold_durations_hours(session, execution_ids)

    items = []
    for r in rows:
        context = quantity_context(r[11], r[10], r[7])
        warning = None
        if context["quantity_mode"] == "quote_contract" and r[1] is None:
            warning = "Missing matches; USD close quantity cannot be reconstructed"
            _logger.warning("Bybit inverse execution %s has no matches", r[0])
        items.append(
            TradeRow(
                execution_id=int(r[0]),
                account_id=int(r[6]),
                account_name=r[9] or f"账户 {r[6]}",
                canonical_symbol=r[7],
                side=r[8],
                close_qty=float(r[1]) if r[1] is not None else None,
                close_price=float(r[2] or 0.0),
                realized_pnl=float(r[3] or 0.0),
                closed_at=r[4],
                hold_duration_hours=hold_map.get(int(r[0])),
                source=r[5],
                **context,
                quantity_warning=warning,
            )
        )

    return TradesResult(
        items=items, total=total, page=page, page_size=page_size
    )
