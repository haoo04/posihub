"""Low-overhead live market prices for the positions page."""

from __future__ import annotations

from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from ..core.logging import get_logger
from ..db.models import Account, Exchange, PositionCurrent, SymbolMapping
from .exchange.ccxt_client import CcxtExchangeClient
from .exchange.factory import resolve_ccxt_options
from .position_market import position_matches_market

_logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class LivePositionPrice:
    position_id: int | None
    account_id: int | None
    canonical_symbol: str
    price: float
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class LivePositionPriceResult:
    prices: list[LivePositionPrice]
    fetched_at: datetime
    failed_exchanges: list[str]


def _fallback_raw_symbol(canonical_symbol: str, account_type: str) -> str:
    """Build the common CCXT symbol form when no explicit mapping exists."""

    upper = (canonical_symbol or "").upper()
    if "/" in upper:
        return upper

    parts = upper.split("-")
    if len(parts) < 2:
        return upper

    base, quote = parts[0], parts[1]
    instrument = parts[2] if len(parts) > 2 else "SPOT"
    if instrument == "SPOT":
        return f"{base}/{quote}"
    if account_type == "coin_perp" and instrument == "PERP":
        return f"{base}/{quote}:{base}"
    return f"{base}/{quote}:{quote}"


def _mapping_candidates(
    session: Session,
    exchange_names: set[str],
    canonical_symbols: set[str],
) -> dict[tuple[str, str], list[str]]:
    if not exchange_names or not canonical_symbols:
        return {}

    rows = session.exec(
        select(SymbolMapping).where(
            SymbolMapping.exchange.in_(sorted(exchange_names)),
            SymbolMapping.canonical_symbol.in_(sorted(canonical_symbols)),
            SymbolMapping.is_active == True,  # noqa: E712
        )
    ).all()
    candidates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        key = (row.exchange.lower(), row.canonical_symbol.upper())
        if row.raw_symbol not in candidates[key]:
            candidates[key].append(row.raw_symbol)
    return candidates


def fetch_live_position_prices(
    session: Session,
    *,
    view: str,
    market: str,
) -> LivePositionPriceResult:
    """Fetch one batched ticker request per exchange/account-type group.

    Prices are intentionally not persisted. The regular account sync remains
    the source of truth for balances and positions, while this short-lived
    public market-data request keeps the dashboard responsive.
    """

    fetched_at = _utcnow()
    all_rows = list(session.exec(select(PositionCurrent)).all())
    accounts = {
        int(row.id): row
        for row in session.exec(select(Account)).all()
        if row.id is not None
    }
    exchanges = {
        int(row.id): row
        for row in session.exec(select(Exchange)).all()
        if row.id is not None
    }
    rows = [
        row
        for row in all_rows
        if row.id is not None
        and position_matches_market(row, accounts.get(int(row.account_id)), market)
        and accounts.get(int(row.account_id)) is not None
        and exchanges.get(accounts[int(row.account_id)].exchange_id) is not None
    ]
    if not rows:
        return LivePositionPriceResult(prices=[], fetched_at=fetched_at, failed_exchanges=[])

    exchange_names = {
        exchanges[accounts[int(row.account_id)].exchange_id].name.lower() for row in rows
    }
    canonical_symbols = {row.canonical_symbol.upper() for row in rows}
    mappings = _mapping_candidates(session, exchange_names, canonical_symbols)

    # A public ticker client can be shared by accounts on the same exchange
    # when their market type is identical. This avoids one request per account.
    groups: dict[tuple[int, str], tuple[Exchange, Account, list[PositionCurrent]]] = {}
    for row in rows:
        account = accounts[int(row.account_id)]
        exchange = exchanges[account.exchange_id]
        key = (int(exchange.id or 0), account.account_type.value)
        if key not in groups:
            groups[key] = (exchange, account, [])
        groups[key][2].append(row)

    prices_by_position: dict[int, LivePositionPrice] = {}
    failed_exchanges: set[str] = set()

    for exchange, account, group_rows in groups.values():
        symbols_by_canonical: dict[str, list[str]] = {}
        requested: list[str] = []
        for row in group_rows:
            canonical = row.canonical_symbol.upper()
            candidates = list(mappings.get((exchange.name.lower(), canonical), []))
            if not candidates:
                candidates = [_fallback_raw_symbol(canonical, account.account_type.value)]
            symbols_by_canonical[canonical] = candidates
            for symbol in candidates:
                if symbol not in requested:
                    requested.append(symbol)

        client = None
        try:
            options = resolve_ccxt_options(account)
            client = CcxtExchangeClient(
                exchange.name,
                default_type=options.default_type,
                default_sub_type=options.default_sub_type,
            )
            raw_prices = client.fetch_last_prices(requested)
            updated_at = _utcnow()
            group_had_missing_price = False
            for row in group_rows:
                candidates = symbols_by_canonical[row.canonical_symbol.upper()]
                price = next(
                    (
                        float(raw_prices.get(symbol) or 0.0)
                        for symbol in candidates
                        if float(raw_prices.get(symbol) or 0.0) > 0
                    ),
                    0.0,
                )
                if price <= 0:
                    group_had_missing_price = True
                    continue
                prices_by_position[int(row.id)] = LivePositionPrice(
                    position_id=int(row.id),
                    account_id=int(row.account_id),
                    canonical_symbol=row.canonical_symbol,
                    price=price,
                    updated_at=updated_at,
                )
            if group_had_missing_price:
                failed_exchanges.add(exchange.name)
        except Exception as exc:
            failed_exchanges.add(exchange.name)
            _logger.warning("live price fetch failed exchange=%s: %s", exchange.name, exc)
        finally:
            if client is not None:
                with suppress(Exception):
                    client.close()

    if view == "split":
        prices = sorted(
            prices_by_position.values(),
            key=lambda item: item.position_id or 0,
        )
        return LivePositionPriceResult(
            prices=prices,
            fetched_at=fetched_at,
            failed_exchanges=sorted(failed_exchanges),
        )

    rows_by_symbol: dict[str, list[PositionCurrent]] = defaultdict(list)
    for row in rows:
        rows_by_symbol[row.canonical_symbol].append(row)

    merged_prices: list[LivePositionPrice] = []
    for canonical, symbol_rows in rows_by_symbol.items():
        live_rows = [
            (row, prices_by_position[int(row.id)])
            for row in symbol_rows
            if row.id is not None and int(row.id) in prices_by_position
        ]
        if not live_rows:
            continue
        total_qty = sum(abs(float(row.qty or 0.0)) for row, _ in live_rows)
        if total_qty > 0:
            price = sum(
                abs(float(row.qty or 0.0)) * live.price for row, live in live_rows
            ) / total_qty
        else:
            price = live_rows[-1][1].price
        updated_at = max(live.updated_at for _, live in live_rows)
        merged_prices.append(
            LivePositionPrice(
                position_id=None,
                account_id=None,
                canonical_symbol=canonical,
                price=price,
                updated_at=updated_at,
            )
        )

    merged_prices.sort(key=lambda item: item.canonical_symbol)
    return LivePositionPriceResult(
        prices=merged_prices,
        fetched_at=fetched_at,
        failed_exchanges=sorted(failed_exchanges),
    )
