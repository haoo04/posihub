"""Symbol mapping management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..db.models import SymbolMapping
from ..schemas.exchange import (
    SymbolMappingCreate,
    SymbolMappingRead,
    SymbolMappingUpdate,
)
from .deps import SessionDep

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])


@router.get("", response_model=list[SymbolMappingRead])
def list_mappings(
    session: SessionDep,
    exchange: str | None = None,
    canonical_symbol: str | None = None,
    is_active: bool | None = None,
) -> list[SymbolMapping]:
    stmt = select(SymbolMapping)
    if exchange is not None:
        stmt = stmt.where(SymbolMapping.exchange == exchange.lower())
    if canonical_symbol is not None:
        stmt = stmt.where(SymbolMapping.canonical_symbol == canonical_symbol)
    if is_active is not None:
        stmt = stmt.where(SymbolMapping.is_active == is_active)
    return list(session.exec(stmt).all())


@router.post(
    "",
    response_model=SymbolMappingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_mapping(
    payload: SymbolMappingCreate, session: SessionDep
) -> SymbolMapping:
    existing = session.exec(
        select(SymbolMapping).where(
            SymbolMapping.exchange == payload.exchange.lower(),
            SymbolMapping.raw_symbol == payload.raw_symbol,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="mapping already exists")

    row = SymbolMapping(
        exchange=payload.exchange.lower(),
        raw_symbol=payload.raw_symbol,
        canonical_symbol=payload.canonical_symbol,
        base_asset=payload.base_asset.upper(),
        quote_asset=payload.quote_asset.upper(),
        instrument_type=payload.instrument_type,
        contract_size=payload.contract_size,
        is_active=payload.is_active,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/upsert", response_model=SymbolMappingRead)
def upsert_mapping(
    payload: SymbolMappingCreate, session: SessionDep
) -> SymbolMapping:
    """Idempotent create-or-update keyed by ``(exchange, raw_symbol)``.

    Useful for resolving symbol-collision conflicts at runtime: re-pointing
    an ambiguous ``raw_symbol`` to a different ``canonical_symbol`` without
    having to delete the existing row first.
    """

    exchange = payload.exchange.lower()
    row = session.exec(
        select(SymbolMapping).where(
            SymbolMapping.exchange == exchange,
            SymbolMapping.raw_symbol == payload.raw_symbol,
        )
    ).first()

    if row is None:
        row = SymbolMapping(
            exchange=exchange,
            raw_symbol=payload.raw_symbol,
            canonical_symbol=payload.canonical_symbol,
            base_asset=payload.base_asset.upper(),
            quote_asset=payload.quote_asset.upper(),
            instrument_type=payload.instrument_type,
            contract_size=payload.contract_size,
            is_active=payload.is_active,
        )
    else:
        row.canonical_symbol = payload.canonical_symbol
        row.base_asset = payload.base_asset.upper()
        row.quote_asset = payload.quote_asset.upper()
        row.instrument_type = payload.instrument_type
        row.contract_size = payload.contract_size
        row.is_active = payload.is_active

    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.patch("/{mapping_id}", response_model=SymbolMappingRead)
def update_mapping(
    mapping_id: int, payload: SymbolMappingUpdate, session: SessionDep
) -> SymbolMapping:
    row = session.get(SymbolMapping, mapping_id)
    if row is None:
        raise HTTPException(status_code=404, detail="mapping not found")

    updates = payload.model_dump(exclude_unset=True)
    if "base_asset" in updates and updates["base_asset"] is not None:
        updates["base_asset"] = updates["base_asset"].upper()
    if "quote_asset" in updates and updates["quote_asset"] is not None:
        updates["quote_asset"] = updates["quote_asset"].upper()

    for field_name, value in updates.items():
        setattr(row, field_name, value)

    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.delete(
    "/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_mapping(mapping_id: int, session: SessionDep) -> None:
    row = session.get(SymbolMapping, mapping_id)
    if row is None:
        raise HTTPException(status_code=404, detail="mapping not found")
    session.delete(row)
    session.commit()
