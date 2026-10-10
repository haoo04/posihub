"""Position aggregation across accounts.

For the *merged* view we combine positions sharing the same
``canonical_symbol``:

- Same direction (long+long or short+short): accumulate quantity, weight the
  entry price by qty, sum unrealized PnL.
- Opposite directions: net the quantity. Resulting side is determined by the
  net sign; entry price is recomputed using the surviving side's weighted
  average. If the net qty is exactly zero, the symbol is omitted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

from ...db.models import PositionSide
from ..pnl_calculator import entry_base_to_quote


@dataclass(slots=True)
class PositionInput:
    account_id: int
    canonical_symbol: str
    side: PositionSide
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    quantity_mode: str = "base"
    quantity_unit: str = ""


@dataclass(slots=True)
class AggregatedPosition:
    canonical_symbol: str
    side: PositionSide
    qty: float
    avg_entry_price: float
    mark_price: float
    unrealized_pnl: float
    realized_pnl: float
    notional: float
    accounts: list[int]
    quantity_mode: str = "base"
    quantity_unit: str = ""


def _signed_qty(side: PositionSide, qty: float) -> float:
    if side == PositionSide.SHORT:
        return -abs(qty)
    return abs(qty)


def aggregate_positions(items: Iterable[PositionInput]) -> list[AggregatedPosition]:
    """Aggregate a flat list of per-account positions by canonical symbol."""

    buckets: dict[tuple[str, str, str], list[PositionInput]] = {}
    for item in items:
        if item.qty == 0:
            continue
        key = (item.canonical_symbol, item.quantity_mode, item.quantity_unit)
        buckets.setdefault(key, []).append(item)

    out: list[AggregatedPosition] = []
    for symbol, group in buckets.items():
        merged = _merge_group(group)
        if merged is not None:
            out.append(merged)

    out.sort(key=lambda p: (-abs(p.notional), p.canonical_symbol))
    return out


def _merge_group(group: list[PositionInput]) -> Optional[AggregatedPosition]:
    long_qty = 0.0
    short_qty = 0.0
    long_cost = 0.0
    short_cost = 0.0
    upnl_total = 0.0
    rpnl_total = 0.0
    accounts: set[int] = set()
    last_mark = 0.0
    inverse = group[0].quantity_mode == "quote_contract"

    for p in group:
        accounts.add(p.account_id)
        upnl_total += p.unrealized_pnl
        rpnl_total += p.realized_pnl
        if p.mark_price:
            last_mark = p.mark_price
        external_qty = entry_base_to_quote(p.qty, p.entry_price) if inverse else p.qty
        signed = _signed_qty(p.side, external_qty)
        if signed > 0:
            long_qty += signed
            long_cost += signed / p.entry_price if inverse else signed * p.entry_price
        elif signed < 0:
            short_qty += -signed  # store as positive
            short_cost += -signed / p.entry_price if inverse else -signed * p.entry_price

    net = long_qty - short_qty
    if net == 0:
        return None

    if net > 0:
        side = PositionSide.LONG
        qty = net
        avg_entry = long_qty / long_cost if inverse else long_cost / long_qty
    else:
        side = PositionSide.SHORT
        qty = -net
        avg_entry = short_qty / short_cost if inverse else short_cost / short_qty

    notional = qty if inverse else qty * (last_mark or avg_entry)
    if side == PositionSide.SHORT:
        notional = -notional

    return AggregatedPosition(
        canonical_symbol=group[0].canonical_symbol,
        side=side,
        qty=qty,
        avg_entry_price=avg_entry,
        mark_price=last_mark,
        unrealized_pnl=upnl_total,
        realized_pnl=rpnl_total,
        notional=notional,
        accounts=sorted(accounts),
        quantity_mode=group[0].quantity_mode,
        quantity_unit=group[0].quantity_unit,
    )
