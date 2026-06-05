"""JSON (de)serialisation for cached preview payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...db.models import PositionSide
from .types import ImportAction, NormalizedHistoryOrder, ClosedPositionSummary


def _dt_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _iso_to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def order_to_dict(order: NormalizedHistoryOrder) -> dict[str, Any]:
    return {
        "source_order_id": order.source_order_id,
        "raw_symbol": order.raw_symbol,
        "canonical_symbol": order.canonical_symbol,
        "side": order.side.value,
        "action": order.action.value,
        "qty": order.qty,
        "price": order.price,
        "created_at": _dt_to_iso(order.created_at),
        "realized_pnl": order.realized_pnl,
        "margin_mode": order.margin_mode,
    }


def order_from_dict(data: dict[str, Any]) -> NormalizedHistoryOrder:
    return NormalizedHistoryOrder(
        source_order_id=data["source_order_id"],
        raw_symbol=data["raw_symbol"],
        canonical_symbol=data.get("canonical_symbol"),
        side=PositionSide(data["side"]),
        action=ImportAction(data["action"]),
        qty=float(data["qty"]),
        price=float(data["price"]),
        created_at=_iso_to_dt(data["created_at"]),
        realized_pnl=data.get("realized_pnl"),
        margin_mode=data.get("margin_mode"),
    )


def closed_position_to_dict(cp: ClosedPositionSummary) -> dict[str, Any]:
    return {
        "raw_symbol": cp.raw_symbol,
        "canonical_symbol": cp.canonical_symbol,
        "side": cp.side.value,
        "close_qty": cp.close_qty,
        "entry_price": cp.entry_price,
        "close_price": cp.close_price,
        "realized_pnl": cp.realized_pnl,
        "open_time": _dt_to_iso(cp.open_time),
        "close_time": _dt_to_iso(cp.close_time),
    }


def closed_position_from_dict(data: dict[str, Any]) -> ClosedPositionSummary:
    return ClosedPositionSummary(
        raw_symbol=data["raw_symbol"],
        canonical_symbol=data.get("canonical_symbol"),
        side=PositionSide(data["side"]),
        close_qty=float(data["close_qty"]),
        entry_price=float(data["entry_price"]),
        close_price=float(data["close_price"]),
        realized_pnl=float(data["realized_pnl"]),
        open_time=_iso_to_dt(data.get("open_time")),
        close_time=_iso_to_dt(data.get("close_time")),
    )
