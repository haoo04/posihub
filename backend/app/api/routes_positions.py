"""Positions endpoints (split + merged views)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import select

from ..db.models import (
    Account,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionOrderMatch,
)
from ..schemas.position import (
    PositionMerged,
    PositionPriceRead,
    PositionPricesRead,
    PositionRead,
)
from ..schemas.position_order import (
    FifoCloseResponse,
    PositionCloseExecutionRead,
    PositionCloseRequest,
    PositionOrderMatchRead,
    PositionOrderRead,
    SpecifiedCloseRequest,
)
from ..services.aggregate.position_aggregator import (
    PositionInput,
    aggregate_positions,
)
from ..services.live_prices import fetch_live_position_prices
from ..services.pnl_calculator import (
    base_asset_from_canonical,
    is_coin_margined_account,
    position_unrealized_pnl_usdt,
)
from ..services.position_market import (
    instrument_type_from_canonical,
    position_matches_market,
)
from ..services.position_order_close import (
    FifoCloseError,
    fifo_close_position,
    specified_close_position,
)
from ..services.realized_pnl_query import realized_pnl_totals_by_position_id
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


@router.get("/prices", response_model=PositionPricesRead)
def list_live_prices(
    session: SessionDep,
    view: str = Query("split", pattern="^(split|merged)$"),
    market: str = Query("derivatives", pattern="^(derivatives|spot)$"),
) -> PositionPricesRead:
    result = fetch_live_position_prices(session, view=view, market=market)
    return PositionPricesRead(
        prices=[PositionPriceRead.model_validate(item) for item in result.prices],
        fetched_at=result.fetched_at,
        failed_exchanges=result.failed_exchanges,
    )


@router.get("", response_model=list[Any])
def list_positions(
    session: SessionDep,
    view: str = Query("split", pattern="^(split|merged)$"),
    market: str = Query("derivatives", pattern="^(derivatives|spot)$"),
) -> list[Any]:
    all_rows = list(session.exec(select(PositionCurrent)).all())
    realized_by_pos = realized_pnl_totals_by_position_id(session)

    accounts = {
        int(a.id): a
        for a in session.exec(select(Account)).all()
        if a.id is not None
    }
    order_counts: dict[int, int] = {
        int(pid): int(count)
        for pid, count in session.exec(
            select(PositionOrder.position_id, func.count())
            .group_by(PositionOrder.position_id)
        ).all()
        if pid is not None
    }
    rows = [
        r
        for r in all_rows
        if position_matches_market(
            r, accounts.get(int(r.account_id)), market
        )
    ]

    if view == "split":
        out: list[PositionRead] = []
        for r in rows:
            pid = int(r.id or 0)
            account = accounts.get(int(r.account_id))
            mark = float(r.mark_price or 0.0)
            entry = float(r.entry_price or 0.0)
            upnl = position_unrealized_pnl_usdt(
                account_type=account.account_type if account else None,
                side=r.side,
                unrealized_pnl=float(r.unrealized_pnl or 0.0),
                mark_price=mark,
            )
            instrument = instrument_type_from_canonical(r.canonical_symbol)
            has_cost_basis = order_counts.get(pid, 0) > 0 or entry > 0
            if instrument.value == "spot" and not has_cost_basis:
                upnl = 0.0

            data = r.model_dump()
            data["unrealized_pnl"] = upnl
            data["realized_pnl"] = float(realized_by_pos.get(pid, 0.0))
            data["instrument_type"] = instrument.value
            data["has_cost_basis"] = has_cost_basis
            if account:
                data["account_type"] = account.account_type.value
                if is_coin_margined_account(account.account_type):
                    data["pnl_asset"] = base_asset_from_canonical(r.canonical_symbol)
            out.append(PositionRead.model_validate(data))
        return out

    inputs = [
        PositionInput(
            account_id=r.account_id,
            canonical_symbol=r.canonical_symbol,
            side=r.side,
            qty=r.qty,
            entry_price=r.entry_price,
            mark_price=r.mark_price,
            unrealized_pnl=position_unrealized_pnl_usdt(
                account_type=accounts.get(int(r.account_id)).account_type
                if accounts.get(int(r.account_id))
                else None,
                side=r.side,
                unrealized_pnl=float(r.unrealized_pnl or 0.0),
                mark_price=float(r.mark_price or 0.0),
            ),
            realized_pnl=float(realized_by_pos.get(int(r.id or 0), 0.0)),
        )
        for r in rows
    ]
    aggregated = aggregate_positions(inputs)
    return [
        PositionMerged(
            canonical_symbol=item.canonical_symbol,
            side=item.side,
            qty=item.qty,
            avg_entry_price=item.avg_entry_price,
            mark_price=item.mark_price,
            unrealized_pnl=item.unrealized_pnl,
            realized_pnl=item.realized_pnl,
            notional=item.notional,
            accounts=item.accounts,
            instrument_type=instrument_type_from_canonical(item.canonical_symbol).value,
        )
        for item in aggregated
    ]


@router.post(
    "/{position_id}/close-fifo",
    response_model=FifoCloseResponse,
    status_code=status.HTTP_201_CREATED,
)
def close_position_fifo(
    session: SessionDep,
    position_id: int,
    payload: PositionCloseRequest,
) -> FifoCloseResponse:
    """Apply a FIFO close to ``position_id``.

    Consumes ``PositionOrder`` rows in ``created_at`` ascending order,
    writes one ``PositionOrderMatch`` per consumed leg, and decrements
    the parent ``PositionCurrent.qty``. The whole operation runs in a
    single transaction.
    """

    try:
        result = fifo_close_position(
            session,
            position_id=position_id,
            close_qty=payload.close_qty,
            close_price=payload.close_price,
            source=payload.source,
            source_order_id=payload.source_order_id,
        )
    except FifoCloseError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    session.commit()
    for order in result.affected_orders:
        session.refresh(order)
    session.refresh(result.execution)

    return FifoCloseResponse(
        execution=PositionCloseExecutionRead.model_validate(result.execution),
        matches=[PositionOrderMatchRead.model_validate(m) for m in result.matches],
        affected_orders=[
            PositionOrderRead.model_validate(o) for o in result.affected_orders
        ],
        realized_pnl=result.realized_pnl,
    )


@router.post(
    "/{position_id}/close-specified",
    response_model=FifoCloseResponse,
    status_code=status.HTTP_201_CREATED,
)
def close_position_specified(
    session: SessionDep,
    position_id: int,
    payload: SpecifiedCloseRequest,
) -> FifoCloseResponse:
    """Close using explicit ``PositionOrder`` legs (non-FIFO order).

    ``legs`` must list each ``open_order_id`` at most once; quantities
    must sum to ``close_qty`` and not exceed each order's ``remaining_qty``.
    """

    try:
        result = specified_close_position(
            session,
            position_id=position_id,
            close_qty=payload.close_qty,
            close_price=payload.close_price,
            legs=[(leg.open_order_id, leg.qty) for leg in payload.legs],
            source=payload.source,
            source_order_id=payload.source_order_id,
        )
    except FifoCloseError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    session.commit()
    for order in result.affected_orders:
        session.refresh(order)
    session.refresh(result.execution)

    return FifoCloseResponse(
        execution=PositionCloseExecutionRead.model_validate(result.execution),
        matches=[PositionOrderMatchRead.model_validate(m) for m in result.matches],
        affected_orders=[
            PositionOrderRead.model_validate(o) for o in result.affected_orders
        ],
        realized_pnl=result.realized_pnl,
    )


@router.get(
    "/{position_id}/matches", response_model=list[PositionOrderMatchRead]
)
def list_position_matches(
    session: SessionDep, position_id: int
) -> list[PositionOrderMatchRead]:
    """List match rows for a given position (newest first)."""

    if session.get(PositionCurrent, position_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    rows = list(
        session.exec(
            select(PositionOrderMatch)
            .join(
                PositionCloseExecution,
                PositionOrderMatch.close_order_id == PositionCloseExecution.id,
            )
            .where(PositionCloseExecution.position_id == position_id)
            .order_by(PositionOrderMatch.matched_at.desc(), PositionOrderMatch.id.desc())
        ).all()
    )
    return [PositionOrderMatchRead.model_validate(r) for r in rows]


@router.get(
    "/{position_id}/close-executions",
    response_model=list[PositionCloseExecutionRead],
)
def list_position_close_executions(
    session: SessionDep, position_id: int
) -> list[PositionCloseExecutionRead]:
    """List close executions for a position (newest first)."""

    if session.get(PositionCurrent, position_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    rows = list(
        session.exec(
            select(PositionCloseExecution)
            .where(PositionCloseExecution.position_id == position_id)
            .order_by(
                PositionCloseExecution.created_at.desc(),
                PositionCloseExecution.id.desc(),
            )
        ).all()
    )
    return [PositionCloseExecutionRead.model_validate(r) for r in rows]
