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

_BITGET_LINEAR_PRODUCT = "USDT-FUTURES"
_BITGET_INVERSE_PRODUCT = "COIN-FUTURES"
_BITGET_INVERSE_MARGIN_FALLBACK = ("BTC", "ETH")

# Bitget rejects history queries spanning more than 90 days, so callers must
# slice longer ranges into windows no wider than this.
_HISTORY_WINDOW_MS = 90 * 24 * 60 * 60 * 1000


def _iter_time_windows(
    since: Optional[int],
    until: Optional[int],
    window_ms: int = _HISTORY_WINDOW_MS,
):
    """Yield ``(since, until)`` slices no wider than ``window_ms`` (epoch ms).

    When ``since`` or ``until`` is missing a single ``(since, until)`` window
    is produced unchanged so connectors can fall back to their own defaults.
    """

    if since is None or until is None or since >= until:
        yield (since, until)
        return
    start = since
    while start < until:
        end = min(start + window_ms, until)
        yield (start, end)
        start = end


def bitget_fetch_params(exchange_name: str, default_sub_type: Optional[str]) -> dict[str, Any]:
    """Explicit Bitget ``productType`` for balance/position API calls."""

    if exchange_name != "bitget":
        return {}
    if default_sub_type == "inverse":
        return {"productType": _BITGET_INVERSE_PRODUCT}
    if default_sub_type == "linear":
        return {"productType": _BITGET_LINEAR_PRODUCT}
    return {}


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
    default_sub_type: Optional[str] = None,
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
    ccxt_options: dict[str, Any] = {}
    if default_type:
        ccxt_options["defaultType"] = default_type
    if default_sub_type:
        ccxt_options["defaultSubType"] = default_sub_type
    if ccxt_options:
        options["options"] = ccxt_options

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
        default_sub_type: Optional[str] = None,
    ) -> None:
        self.exchange_name = exchange_id
        self._default_type = default_type
        self._default_sub_type = default_sub_type
        self._client = _build_exchange(
            exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            default_type=default_type,
            default_sub_type=default_sub_type,
        )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def _fetch_params(self) -> dict[str, Any]:
        return bitget_fetch_params(self.exchange_name, self._default_sub_type)

    def fetch_balance(self) -> list[RawBalance]:
        params = self._fetch_params()
        raw = call_with_retry(
            lambda: self._client.fetch_balance(params),
            label=f"{self.exchange_name}.fetch_balance",
        )
        return self._parse_balance(raw)

    def fetch_positions(self) -> list[RawPosition]:
        if not getattr(self._client, "has", {}).get("fetchPositions"):
            return []

        if self.exchange_name == "bitget" and self._default_sub_type == "inverse":
            raw = self._fetch_bitget_coin_futures_positions()
        else:
            params = self._fetch_params()
            raw = call_with_retry(
                lambda: self._client.fetch_positions(params=params),
                label=f"{self.exchange_name}.fetch_positions",
            )
        return self._parse_positions(raw or [])

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        if not symbols:
            return {}

        normalized = [s for s in symbols if s]
        if not normalized:
            return {}

        has_tickers = bool(getattr(self._client, "has", {}).get("fetchTickers"))
        if has_tickers:
            try:
                params = self._fetch_params()
                raw = call_with_retry(
                    lambda: self._client.fetch_tickers(normalized, params),
                    label=f"{self.exchange_name}.fetch_tickers",
                )
                return self._parse_ticker_prices(raw or {}, normalized)
            except Exception as exc:
                _logger.debug(
                    "%s fetch_tickers batch failed, falling back: %s",
                    self.exchange_name,
                    exc,
                )

        out: dict[str, float] = {}
        for symbol in normalized:
            try:
                params = self._fetch_params()
                ticker = call_with_retry(
                    lambda s=symbol, p=params: self._client.fetch_ticker(s, p),
                    label=f"{self.exchange_name}.fetch_ticker[{symbol}]",
                )
                price = self._extract_ticker_price(ticker or {})
                if price > 0:
                    out[symbol] = price
            except Exception as exc:
                _logger.debug(
                    "%s fetch_ticker symbol=%s skipped: %s",
                    self.exchange_name,
                    symbol,
                    exc,
                )
        return out

    @staticmethod
    def _extract_ticker_price(raw: dict[str, Any]) -> float:
        for key in ("last", "close", "bid", "ask"):
            value = raw.get(key)
            if value is not None:
                try:
                    price = float(value)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    return price
        return 0.0

    @classmethod
    def _parse_ticker_prices(
        cls, raw: dict[str, Any], requested: list[str]
    ) -> dict[str, float]:
        out: dict[str, float] = {}
        for symbol in requested:
            ticker = raw.get(symbol)
            if not isinstance(ticker, dict):
                continue
            price = cls._extract_ticker_price(ticker)
            if price > 0:
                out[symbol] = price
        return out

    def _discover_bitget_coin_margin_coins(self) -> list[str]:
        """List margin coins for Bitget COIN-FUTURES (inverse) wallets."""

        try:
            response = call_with_retry(
                lambda: self._client.privateMixGetV2MixAccountAccounts(
                    {"productType": _BITGET_INVERSE_PRODUCT}
                ),
                label=f"{self.exchange_name}.mix_accounts[COIN-FUTURES]",
            )
        except Exception as exc:
            _logger.warning("bitget COIN-FUTURES account list failed: %s", exc)
            return list(_BITGET_INVERSE_MARGIN_FALLBACK)

        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, list):
            return list(_BITGET_INVERSE_MARGIN_FALLBACK)

        coins: list[str] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            coin = entry.get("marginCoin")
            if coin:
                coins.append(str(coin).upper())

        if not coins:
            return list(_BITGET_INVERSE_MARGIN_FALLBACK)
        return coins

    def _fetch_bitget_coin_futures_positions(self) -> list[dict[str, Any]]:
        """Fetch inverse positions per margin coin.

        CCXT defaults ``marginCoin`` to ``USDT`` for ``fetch_positions``, which
        Bitget rejects for ``COIN-FUTURES`` (error 40778). Query each wallet
        coin returned by the mix account list API instead.
        """

        margin_coins = self._discover_bitget_coin_margin_coins()

        # Merge coins that still have wallet equity (covers edge cases).
        try:
            balance = call_with_retry(
                lambda: self._client.fetch_balance(
                    {"productType": _BITGET_INVERSE_PRODUCT}
                ),
                label=f"{self.exchange_name}.fetch_balance[COIN-FUTURES]",
            )
            for asset, amount in (balance.get("total") or {}).items():
                if float(amount or 0) > 0:
                    upper = str(asset).upper()
                    if upper not in margin_coins:
                        margin_coins.append(upper)
        except Exception as exc:
            _logger.debug("bitget COIN-FUTURES balance probe skipped: %s", exc)

        all_positions: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        for coin in margin_coins:
            pos_params = {
                "productType": _BITGET_INVERSE_PRODUCT,
                "marginCoin": coin,
            }
            try:
                batch = call_with_retry(
                    lambda p=pos_params: self._client.fetch_positions(params=p),
                    label=f"{self.exchange_name}.fetch_positions[{coin}]",
                )
            except Exception as exc:
                _logger.debug("bitget positions marginCoin=%s skipped: %s", coin, exc)
                continue

            for pos in batch or []:
                symbol = str(pos.get("symbol") or pos.get("info", {}).get("symbol") or "")
                side = str(pos.get("side") or "net").lower()
                key = (symbol, side)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_positions.append(pos)

        return all_positions

    def fetch_markets(self) -> list[RawMarket]:
        markets = call_with_retry(
            self._client.load_markets,
            label=f"{self.exchange_name}.load_markets",
        )
        return self._parse_markets(markets or {})

    def fetch_positions_history(
        self,
        *,
        since: Optional[int] = None,
        until: Optional[int] = None,
        symbols: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        if not getattr(self._client, "has", {}).get("fetchPositionsHistory"):
            return []

        out: list[dict[str, Any]] = []
        for window_since, window_until in _iter_time_windows(since, until):
            params = dict(self._fetch_params())
            if window_until is not None:
                params["until"] = window_until
            try:
                batch = call_with_retry(
                    lambda s=window_since, p=params: self._client.fetch_positions_history(
                        symbols, s, None, p
                    ),
                    label=f"{self.exchange_name}.fetch_positions_history",
                )
            except Exception as exc:
                _logger.warning(
                    "%s fetch_positions_history window skipped: %s",
                    self.exchange_name,
                    exc,
                )
                continue
            out.extend(batch or [])
        return out

    def fetch_closed_orders_history(
        self,
        *,
        since: Optional[int] = None,
        until: Optional[int] = None,
        symbols: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        if not getattr(self._client, "has", {}).get("fetchClosedOrders"):
            return []

        # Bitget requires a symbol for contract order history; iterate the
        # discovered symbols. A ``None`` symbol lets exchanges that support an
        # account-wide query return everything in one pass.
        target_symbols: list[Optional[str]] = list(symbols) if symbols else [None]

        out: list[dict[str, Any]] = []
        for symbol in target_symbols:
            for window_since, window_until in _iter_time_windows(since, until):
                params = dict(self._fetch_params())
                if window_until is not None:
                    params["until"] = window_until
                try:
                    batch = call_with_retry(
                        lambda sym=symbol, s=window_since, p=params: self._client.fetch_closed_orders(
                            sym, s, None, p
                        ),
                        label=f"{self.exchange_name}.fetch_closed_orders[{symbol}]",
                    )
                except Exception as exc:
                    _logger.warning(
                        "%s fetch_closed_orders symbol=%s window skipped: %s",
                        self.exchange_name,
                        symbol,
                        exc,
                    )
                    continue
                out.extend(batch or [])
        return out

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
