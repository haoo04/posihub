"""Read-only CCXT-backed exchange connector.

Wraps :mod:`ccxt` 4.5.x. Designed strictly for read-only API keys: only
:meth:`fetch_balance`, :meth:`fetch_positions` and :meth:`fetch_markets` are
exposed. No order placement / withdrawal endpoints are reachable from this
class, providing defence-in-depth even if a key was misconfigured.
"""

from __future__ import annotations

from typing import Any, Optional

import ccxt

from ...core.logging import get_logger
from .base import ExchangeClient, RawBalance, RawMarket, RawPosition
from .retry import call_with_retry

_logger = get_logger(__name__)


class UnsupportedExchange(RuntimeError):
    """Raised when the requested exchange id is not provided by ccxt."""


def list_supported_exchanges() -> list[str]:
    """Return ccxt's exchange id list (sorted)."""

    return sorted(ccxt.exchanges)


def _build_exchange(
    exchange_id: str,
    *,
    api_key: Optional[str],
    api_secret: Optional[str],
    passphrase: Optional[str],
    default_type: Optional[str],
) -> Any:
    if exchange_id not in ccxt.exchanges:
        raise UnsupportedExchange(f"ccxt does not support exchange '{exchange_id}'")

    klass = getattr(ccxt, exchange_id)
    options: dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": 15_000,
    }
    if api_key:
        options["apiKey"] = api_key
    if api_secret:
        options["secret"] = api_secret
    if passphrase:
        options["password"] = passphrase
    if default_type:
        options["options"] = {"defaultType": default_type}

    return klass(options)


class CcxtExchangeClient(ExchangeClient):
    """Read-only CCXT exchange connector with retry."""

    def __init__(
        self,
        exchange_id: str,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        default_type: Optional[str] = None,
    ) -> None:
        self.exchange_name = exchange_id
        self._default_type = default_type
        self._client = _build_exchange(
            exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            default_type=default_type,
        )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def fetch_balance(self) -> list[RawBalance]:
        raw = call_with_retry(
            self._client.fetch_balance,
            label=f"{self.exchange_name}.fetch_balance",
        )
        return self._parse_balance(raw)

    def fetch_positions(self) -> list[RawPosition]:
        if not getattr(self._client, "has", {}).get("fetchPositions"):
            return []

        raw = call_with_retry(
            lambda: self._client.fetch_positions(),
            label=f"{self.exchange_name}.fetch_positions",
        )
        return self._parse_positions(raw or [])

    def fetch_markets(self) -> list[RawMarket]:
        markets = call_with_retry(
            self._client.load_markets,
            label=f"{self.exchange_name}.load_markets",
        )
        return self._parse_markets(markets or {})

    def close(self) -> None:
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception as exc:  # pragma: no cover
                _logger.debug("close() ignored: %s", exc)

    # ------------------------------------------------------------------
    # parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_balance(raw: dict[str, Any]) -> list[RawBalance]:
        items: list[RawBalance] = []
        free = raw.get("free") or {}
        used = raw.get("used") or {}
        total = raw.get("total") or {}

        assets = set(free) | set(used) | set(total)
        for asset in sorted(assets):
            equity = float(total.get(asset) or 0.0)
            available = float(free.get(asset) or 0.0)
            frozen = float(used.get(asset) or 0.0)
            if equity == 0.0 and available == 0.0 and frozen == 0.0:
                continue
            items.append(
                RawBalance(
                    asset=asset.upper(),
                    equity=equity,
                    available=available,
                    frozen=frozen,
                )
            )
        return items

    @staticmethod
    def _parse_positions(raw_list: list[dict[str, Any]]) -> list[RawPosition]:
        positions: list[RawPosition] = []
        for raw in raw_list:
            if raw is None:
                continue
            symbol = raw.get("symbol") or raw.get("info", {}).get("symbol")
            if not symbol:
                continue

            qty = float(raw.get("contracts") or raw.get("amount") or 0.0)
            if qty == 0.0:
                continue

            side = (raw.get("side") or "net").lower()
            entry = float(raw.get("entryPrice") or raw.get("entry_price") or 0.0)
            mark = float(
                raw.get("markPrice") or raw.get("mark_price") or raw.get("lastPrice") or 0.0
            )
            upnl = float(raw.get("unrealizedPnl") or raw.get("unrealized_pnl") or 0.0)
            leverage = float(raw.get("leverage") or 1.0)
            margin_mode = raw.get("marginMode") or raw.get("margin_mode")
            contract_size = float(raw.get("contractSize") or 1.0)

            positions.append(
                RawPosition(
                    raw_symbol=str(symbol),
                    side=side,
                    qty=qty,
                    entry_price=entry,
                    mark_price=mark,
                    unrealized_pnl=upnl,
                    leverage=leverage,
                    margin_mode=margin_mode,
                    contract_size=contract_size,
                )
            )
        return positions

    @staticmethod
    def _parse_markets(markets: dict[str, dict[str, Any]]) -> list[RawMarket]:
        out: list[RawMarket] = []
        for symbol, info in markets.items():
            if not isinstance(info, dict):
                continue
            base = (info.get("base") or "").upper()
            quote = (info.get("quote") or info.get("settle") or "").upper()
            if not base or not quote:
                continue

            instrument = "spot"
            if info.get("swap"):
                instrument = "perp"
            elif info.get("future"):
                instrument = "futures"
            elif info.get("type") in {"swap", "future", "spot"}:
                instrument = info.get("type", "spot")
                if instrument == "swap":
                    instrument = "perp"
                elif instrument == "future":
                    instrument = "futures"

            out.append(
                RawMarket(
                    raw_symbol=str(symbol),
                    base_asset=base,
                    quote_asset=quote,
                    instrument_type=instrument,
                    contract_size=float(info.get("contractSize") or 1.0),
                )
            )
        return out
