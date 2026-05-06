"""Positions endpoints (split + merged views)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlmodel import select

from ..db.models import PositionCurrent
from ..schemas.position import PositionMerged, PositionRead
from ..services.aggregate.position_aggregator import (
    PositionInput,
    aggregate_positions,
)
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
