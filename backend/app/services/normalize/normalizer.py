"""Normalises raw exchange data into ORM-ready records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlmodel import Session

from ...db.models import (
    AccountBalanceCurrent,
    DataSource,
    InstrumentType,
    PositionCurrent,
    PositionSide,
)
from ..exchange.base import RawBalance, RawPosition
from .symbol_mapper import CanonicalSymbol, SymbolMapper


@dataclass(slots=True)
class NormalizedBalance:
    account_id: int
    asset: str
    equity: float
    available: float
    frozen: float
    source: DataSource = DataSource.API
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class NormalizedPosition:
    account_id: int
    canonical_symbol: str
    side: PositionSide
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float
    margin_mode: Optional[str]
    source: DataSource = DataSource.API
    updated_at: datetime = field(default_factory=_utcnow)
    raw_symbol: str = ""


def _to_side(value: str) -> PositionSide:
    text = (value or "").lower()
    if text == "long":
        return PositionSide.LONG
    if text == "short":
        return PositionSide.SHORT
    return PositionSide.NET


def normalize_balances(
    *,
    account_id: int,
    raws: list[RawBalance],
    source: DataSource = DataSource.API,
) -> list[NormalizedBalance]:
    now = _utcnow()
    return [
        NormalizedBalance(
            account_id=account_id,
            asset=raw.asset.upper(),
            equity=raw.equity,
            available=raw.available,
            frozen=raw.frozen,
            source=source,
            updated_at=now,
        )
        for raw in raws
    ]


def normalize_positions(
    *,
    account_id: int,
    exchange_name: str,
    raws: list[RawPosition],
    mapper: SymbolMapper,
    source: DataSource = DataSource.API,
) -> list[NormalizedPosition]:
    now = _utcnow()
    out: list[NormalizedPosition] = []

    for raw in raws:
        canonical = mapper.resolve(
            exchange_name,
            raw.raw_symbol,
            instrument_hint="perp",
            contract_size=raw.contract_size,
        )
        if canonical is None:
            canonical = CanonicalSymbol(
                canonical=raw.raw_symbol,
                base_asset="",
                quote_asset="",
                instrument_type=InstrumentType.PERP,
                contract_size=raw.contract_size,
            )

        out.append(
            NormalizedPosition(
                account_id=account_id,
                canonical_symbol=canonical.canonical,
                side=_to_side(raw.side),
                qty=raw.qty,
                entry_price=raw.entry_price,
                mark_price=raw.mark_price,
                unrealized_pnl=raw.unrealized_pnl,
                leverage=raw.leverage,
                margin_mode=raw.margin_mode,
                source=source,
                updated_at=now,
                raw_symbol=raw.raw_symbol,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def upsert_balances(
    session: Session, account_id: int, items: list[NormalizedBalance]
) -> int:
    """Replace current balances for the account; returns number of rows."""

    from sqlalchemy import delete

    session.exec(  # type: ignore[call-arg]
        delete(AccountBalanceCurrent).where(
            AccountBalanceCurrent.account_id == account_id
        )
    )
    for item in items:
        session.add(
            AccountBalanceCurrent(
                account_id=item.account_id,
                asset=item.asset,
                equity=item.equity,
                available=item.available,
                frozen=item.frozen,
                source=item.source,
                updated_at=item.updated_at,
            )
        )
    return len(items)


def upsert_positions(
    session: Session, account_id: int, items: list[NormalizedPosition]
) -> int:
    """Replace current positions for the account; returns number of rows."""

    from sqlalchemy import delete

    session.exec(  # type: ignore[call-arg]
        delete(PositionCurrent).where(PositionCurrent.account_id == account_id)
    )
    for item in items:
        session.add(
            PositionCurrent(
                account_id=item.account_id,
                canonical_symbol=item.canonical_symbol,
                side=item.side,
                qty=item.qty,
                entry_price=item.entry_price,
                mark_price=item.mark_price,
                unrealized_pnl=item.unrealized_pnl,
                leverage=item.leverage,
                margin_mode=item.margin_mode,
                source=item.source,
                updated_at=item.updated_at,
            )
        )
    return len(items)
