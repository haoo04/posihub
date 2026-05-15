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
    unmapped: Optional[list[str]] = None,
) -> list[NormalizedPosition]:
    """Map raw positions to :class:`NormalizedPosition`.

    If ``unmapped`` is provided, any ``raw_symbol`` that could not be resolved
    via the whitelist or heuristic is appended to it. The position itself is
    still emitted, falling back to the raw symbol as canonical so the user
    sees the data and can decide to add a mapping later.
    """

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
            if unmapped is not None:
                unmapped.append(raw.raw_symbol)
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


def merge_positions(
    items: list[NormalizedPosition],
) -> list[NormalizedPosition]:
    """Merge positions sharing the same ``(canonical_symbol, side)``.

    Two raw symbols on the same exchange can map to a single canonical key
    (e.g. after a symbol-mapping whitelist update). The ``PositionCurrent``
    table enforces ``UniqueConstraint(account_id, canonical_symbol, side)``,
    so we collapse such duplicates before persistence.

    Merge rules:
    - ``qty``, ``unrealized_pnl``: summed.
    - ``entry_price``: quantity-weighted average (falls back to first non-zero
      entry when total qty is zero).
    - ``mark_price``: quantity-weighted average across non-zero-qty legs
      (latest non-zero otherwise).
    - ``leverage``, ``margin_mode``: first non-zero / non-null wins.
    - ``raw_symbol``: kept from the first leg for traceability.
    """

    if not items:
        return items

    grouped: dict[tuple[str, PositionSide], list[NormalizedPosition]] = {}
    order: list[tuple[str, PositionSide]] = []
    for item in items:
        key = (item.canonical_symbol, item.side)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(item)

    merged: list[NormalizedPosition] = []
    for key in order:
        legs = grouped[key]
        if len(legs) == 1:
            merged.append(legs[0])
            continue

        total_qty = sum(leg.qty for leg in legs)
        weighted_entry = sum(leg.entry_price * leg.qty for leg in legs)
        weighted_mark = sum(leg.mark_price * leg.qty for leg in legs)
        unrealized = sum(leg.unrealized_pnl for leg in legs)

        if total_qty != 0:
            entry_price = weighted_entry / total_qty
            mark_price = weighted_mark / total_qty
        else:
            entry_price = next((leg.entry_price for leg in legs if leg.entry_price), 0.0)
            mark_price = next((leg.mark_price for leg in legs if leg.mark_price), 0.0)

        leverage = next((leg.leverage for leg in legs if leg.leverage), legs[0].leverage)
        margin_mode = next(
            (leg.margin_mode for leg in legs if leg.margin_mode), legs[0].margin_mode
        )

        merged.append(
            NormalizedPosition(
                account_id=legs[0].account_id,
                canonical_symbol=legs[0].canonical_symbol,
                side=legs[0].side,
                qty=total_qty,
                entry_price=entry_price,
                mark_price=mark_price,
                unrealized_pnl=unrealized,
                leverage=leverage,
                margin_mode=margin_mode,
                source=legs[0].source,
                updated_at=legs[0].updated_at,
                raw_symbol=legs[0].raw_symbol,
            )
        )
    return merged


def upsert_positions(
    session: Session, account_id: int, items: list[NormalizedPosition]
) -> int:
    """Replace current positions for the account; returns number of rows."""

    from sqlalchemy import delete

    session.exec(  # type: ignore[call-arg]
        delete(PositionCurrent).where(PositionCurrent.account_id == account_id)
    )
    merged = merge_positions(items)
    for item in merged:
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
    return len(merged)
