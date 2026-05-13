"""Positions endpoints (split + merged views)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from ..db.models import (
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
    PositionOrderMatch,
)
from ..schemas.position import PositionMerged, PositionRead
from ..schemas.position_order import (
    FifoCloseResponse,
    PositionCloseExecutionRead,
    PositionCloseRequest,
    PositionOrderMatchRead,
    PositionOrderRead,
)
from ..services.aggregate.position_aggregator import (
    PositionInput,
    aggregate_positions,
)
from ..services.position_order_close import FifoCloseError, fifo_close_position
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


@router.get("", response_model=list[Any])
def list_positions(
    session: SessionDep,
    view: str = Query("split", pattern="^(split|merged)$"),
) -> list[Any]:
    rows = list(session.exec(select(PositionCurrent)).all())

    if view == "split":
        return [PositionRead.model_validate(r) for r in rows]

    inputs = [
        PositionInput(
            account_id=r.account_id,
            canonical_symbol=r.canonical_symbol,
            side=r.side,
            qty=r.qty,
            entry_price=r.entry_price,
            mark_price=r.mark_price,
            unrealized_pnl=r.unrealized_pnl,
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
            notional=item.notional,
            accounts=item.accounts,
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


@router.get(
    "/{position_id}/matches", response_model=list[PositionOrderMatchRead]
)
def list_position_matches(
    session: SessionDep, position_id: int
) -> list[PositionOrderMatchRead]:
    """List FIFO match rows for a given position (newest first)."""

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
    """List all FIFO close executions for a position (newest first)."""

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
