"""Normalises raw exchange data into ORM-ready records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlmodel import Session, select

from ...db.models import (
    AccountBalanceCurrent,
    DataSource,
    InstrumentType,
    PositionCloseExecution,
    PositionCurrent,
    PositionOrder,
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


def _load_balances_by_asset(
    session: Session, account_id: int
) -> dict[str, AccountBalanceCurrent]:
    rows = session.exec(
        select(AccountBalanceCurrent).where(
            AccountBalanceCurrent.account_id == account_id
        )
    ).all()
    return {row.asset: row for row in rows}


def _load_positions_by_key(
    session: Session, account_id: int
) -> dict[tuple[str, PositionSide], PositionCurrent]:
    rows = session.exec(
        select(PositionCurrent).where(PositionCurrent.account_id == account_id)
    ).all()
    return {(row.canonical_symbol, row.side): row for row in rows}


def _position_has_children(session: Session, position_id: int) -> bool:
    """True when order-level rows still reference this position."""

    if (
        session.exec(
            select(PositionOrder.id)
            .where(PositionOrder.position_id == position_id)
            .limit(1)
        ).first()
        is not None
    ):
        return True
    return (
        session.exec(
            select(PositionCloseExecution.id)
            .where(PositionCloseExecution.position_id == position_id)
            .limit(1)
        ).first()
        is not None
    )


def upsert_balances(
    session: Session, account_id: int, items: list[NormalizedBalance]
) -> int:
    """Upsert current balances by ``(account_id, asset)``, preserving row ids."""

    existing = _load_balances_by_asset(session, account_id)
    incoming_assets: set[str] = set()

    for item in items:
        incoming_assets.add(item.asset)
        row = existing.get(item.asset)
        if row is None:
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
            continue

        row.equity = item.equity
        row.available = item.available
        row.frozen = item.frozen
        row.source = item.source
        row.updated_at = item.updated_at
        session.add(row)

    for asset, row in existing.items():
        if asset not in incoming_assets:
            session.delete(row)

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


def _apply_position_fields(row: PositionCurrent, item: NormalizedPosition) -> None:
    row.qty = item.qty
    row.entry_price = item.entry_price
    row.mark_price = item.mark_price
    row.unrealized_pnl = item.unrealized_pnl
    row.leverage = item.leverage
    row.margin_mode = item.margin_mode
    row.source = item.source
    row.updated_at = item.updated_at


def upsert_positions(
    session: Session, account_id: int, items: list[NormalizedPosition]
) -> int:
    """Upsert positions by ``(account_id, canonical_symbol, side)``.

    Existing ``positions_current.id`` values are preserved so
    ``position_orders.position_id`` remains valid across syncs. Rows absent
    from the latest fetch are deleted only when no order-level children exist;
    otherwise they are zeroed out to keep FK integrity.
    """

    merged = merge_positions(items)
    existing = _load_positions_by_key(session, account_id)
    incoming_keys: set[tuple[str, PositionSide]] = set()

    for item in merged:
        key = (item.canonical_symbol, item.side)
        incoming_keys.add(key)
        row = existing.get(key)
        if row is None:
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
            continue

        _apply_position_fields(row, item)
        session.add(row)

    for key, row in existing.items():
        if key in incoming_keys:
            continue
        if row.id is not None and _position_has_children(session, row.id):
            row.qty = 0.0
            row.unrealized_pnl = 0.0
            row.updated_at = _utcnow()
            session.add(row)
        else:
            session.delete(row)

    return len(merged)
