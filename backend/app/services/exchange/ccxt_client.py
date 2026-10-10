"""Read-only CCXT-backed exchange connector.

Wraps :mod:`ccxt` 4.5.x. Designed strictly for read-only API keys: only
:meth:`fetch_balance`, :meth:`fetch_positions` and :meth:`fetch_markets` are
exposed. No order placement / withdrawal endpoints are reachable from this
class, providing defence-in-depth even if a key was misconfigured.
"""

from __future__ import annotations

import math
import time
from typing import Any, Optional

import ccxt

from ...core.logging import get_logger
from .base import ExchangeClient, FetchResult, RawBalance, RawMarket, RawPosition
from .retry import call_with_retry

_logger = get_logger(__name__)

_BITGET_LINEAR_PRODUCT = "USDT-FUTURES"
_BITGET_INVERSE_PRODUCT = "COIN-FUTURES"
_BITGET_INVERSE_MARGIN_FALLBACK = ("BTC", "ETH")

# Bitget rejects history queries spanning more than 90 days, so callers must
# slice longer ranges into windows no wider than this.
_HISTORY_WINDOW_MS = 90 * 24 * 60 * 60 * 1000
_UTA_HISTORY_WINDOW_MS = 30 * 24 * 60 * 60 * 1000


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


def _history_row_key(raw: Any, *, kind: str) -> str | None:
    """Return a stable exchange id for cross-window/page de-duplication."""

    if not isinstance(raw, dict):
        return None
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    if kind == "trade":
        value = raw.get("id") or info.get("tradeId") or info.get("execId")
    elif kind == "position":
        value = raw.get("id") or info.get("positionId")
    else:
        value = raw.get("id") or info.get("orderId")
    return str(value) if value is not None and str(value) else None


def _deduplicate_history_rows(rows: list[dict[str, Any]], *, kind: str) -> list[dict[str, Any]]:
    """Keep one row per order/trade id while preserving exchange order."""

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        key = _history_row_key(raw, kind=kind)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        out.append(raw)
    return out


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
    uta: bool = False,
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
    if exchange_id == "bitget":
        ccxt_options["uta"] = uta
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
        uta: bool = False,
        history_product_type: str = _BITGET_LINEAR_PRODUCT,
    ) -> None:
        self.exchange_name = exchange_id
        self._default_type = default_type
        self._default_sub_type = default_sub_type
        self._uta = uta and exchange_id == "bitget"
        self._history_product_type = history_product_type
        if uta and exchange_id != "bitget":
            raise ValueError("UTA is only supported by Bitget")
        self._client = _build_exchange(
            exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            default_type=default_type,
            default_sub_type=default_sub_type,
            uta=self._uta,
        )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def _fetch_params(self) -> dict[str, Any]:
        if self._uta:
            return {"uta": True}
        return bitget_fetch_params(self.exchange_name, self._default_sub_type)

    def fetch_balance(self) -> list[RawBalance]:
        if self._uta:
            return self._fetch_uta_assets()[1]
        params = self._fetch_params()
        raw = call_with_retry(
            lambda: self._client.fetch_balance(params),
            label=f"{self.exchange_name}.fetch_balance",
        )
        return self._parse_balance(raw)

    def fetch_positions(self) -> list[RawPosition]:
        if self._uta:
            return self._fetch_uta_positions(_BITGET_LINEAR_PRODUCT) + self._fetch_uta_positions(
                _BITGET_INVERSE_PRODUCT
            )
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

    def _bitget_read(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = call_with_retry(
                lambda: getattr(self._client, method)(params), label=f"bitget.{method}",
                redact_errors=True,
            )
        except Exception as exc:
            # Private exception strings can contain signed requests or responses.
            raise RuntimeError(f"Bitget read failed: {method} ({type(exc).__name__})") from None
        if not isinstance(response, dict) or response.get("code") != "00000":
            raise RuntimeError(f"Invalid Bitget response: {method}")
        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid Bitget data: {method}")
        return data

    def _fetch_uta_assets(self) -> tuple[dict[str, Any], list[RawBalance]]:
        data = self._bitget_read("privateUtaGetV3AccountAssets", {})
        try:
            equity = float(data["usdtEquity"])
            if not math.isfinite(equity) or equity < 0 or not isinstance(data["assets"], list):
                raise ValueError
            balances = [
                RawBalance(
                    asset=str(row["coin"]).upper(),
                    equity=float(row["equity"]),
                    available=float(row["available"]),
                    frozen=float(row["locked"]),
                    wallet_balance=float(row["balance"]),
                    usd_value=float(row["usdValue"]),
                    debt=float(row["debt"]),
                )
                for row in data["assets"]
            ]
            for balance in balances:
                if not balance.asset or not all(
                    math.isfinite(value)
                    for value in (
                        balance.equity, balance.available, balance.frozen,
                        balance.wallet_balance, balance.usd_value, balance.debt,
                    )
                ):
                    raise ValueError
            if len({balance.asset for balance in balances}) != len(balances):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Invalid Bitget UTA assets or total equity") from None
        return data, balances

    def _fetch_uta_positions(self, category: str) -> list[RawPosition]:
        try:
            rows = call_with_retry(
                lambda: self._client.fetch_positions(params={"uta": True, "category": category}),
                label=f"bitget.uta_positions[{category}]",
                redact_errors=True,
            )
            if not isinstance(rows, list):
                raise ValueError
            for row in rows:
                if not isinstance(row, dict) or not row.get("symbol"):
                    raise ValueError
                quantity = row.get("contracts") if row.get("contracts") is not None else row.get("amount")
                if quantity is None or not math.isfinite(float(quantity)):
                    raise ValueError
                if float(quantity) == 0:
                    continue
                if (row.get("info") or {}).get("category", category) != category:
                    raise ValueError
                if row.get("side") not in {"long", "short"}:
                    raise ValueError
            positions = self._parse_positions(rows)
            for position in positions:
                position.product_type = category
                if not all(math.isfinite(value) for value in (
                    position.qty, position.entry_price, position.mark_price,
                    position.unrealized_pnl, position.leverage,
                )) or position.qty < 0 or position.entry_price <= 0 or position.mark_price <= 0:
                    raise ValueError
            return positions
        except Exception as exc:
            raise RuntimeError(f"Bitget UTA positions failed: {category} ({type(exc).__name__})") from None

    def fetch_all(self) -> FetchResult:
        if not self._uta:
            return super().fetch_all()
        data, balances = self._fetch_uta_assets()
        positions = self.fetch_positions()
        if any(balance.debt != 0 for balance in balances):
            raise RuntimeError("Unsupported Bitget UTA debt")
        if self._fetch_uta_positions("USDC-FUTURES"):
            raise RuntimeError("Unsupported Bitget UTA USDC-FUTURES exposure")
        return FetchResult(balances, positions, float(data["usdtEquity"]))

    def fetch_account_details(self) -> dict[str, Any]:
        if self.exchange_name != "bitget":
            return {}
        method = "privateUtaGetV3AccountInfo" if self._uta else "privateSpotGetV2SpotAccountInfo"
        info = self._bitget_read(method, {})
        uid = str(info.get("userId") or info.get("uid") or "")
        blockers = [] if uid else ["Bitget UID unavailable"]
        details: dict[str, Any] = {"uid": uid, "blockers": blockers, "warnings": []}
        if not self._uta:
            return details
        settings = self._bitget_read("privateUtaGetV3AccountSettings", {})
        details.update(
            account_mode=settings.get("accountMode"),
            account_level=settings.get("accountLevel"),
            hold_mode=settings.get("holdMode"),
            permission_type=info.get("permType"),
            permissions=info.get("permissions", []),
        )
        if str(settings.get("uid") or "") != uid:
            blockers.append("Bitget UID differs between account info and settings")
        if settings.get("accountMode") not in {"unified", "hybrid"}:
            blockers.append("UTA account must be stable: unified or hybrid")
        if settings.get("accountLevel") != "advanced":
            blockers.append("UTA Advanced Mode is required")
        if settings.get("holdMode") not in {"one_way_mode", "hedge_mode"}:
            blockers.append("Unsupported UTA holding mode")
        permissions = info.get("permissions", [])
        if info.get("permType") != "read-only" or "withdraw" in permissions:
            blockers.append("A read-only key without withdrawal permission is required")
        if not {"uta_mgt", "uta_trade"}.issubset(permissions):
            blockers.append("UTA management and trade read permissions are required")
        data, balances = self._fetch_uta_assets()
        self._fetch_uta_positions(_BITGET_LINEAR_PRODUCT)
        self._fetch_uta_positions(_BITGET_INVERSE_PRODUCT)
        if self._fetch_uta_positions("USDC-FUTURES"):
            blockers.append("USDC-FUTURES exposure is outside the supported scope")
        if any(balance.debt != 0 for balance in balances):
            blockers.append("Nonzero debt is outside the supported scope")
        account_equity = float(data.get("accountEquity", "nan"))
        usd_sum = sum(balance.usd_value or 0 for balance in balances)
        if not math.isfinite(account_equity) or abs(usd_sum - account_equity) > max(
            1.0, abs(account_equity) * 0.001
        ):
            blockers.append("UTA asset valuation does not reconcile")
        details["capabilities"] = ["spot", "usdt_perp", "coin_perp"]
        return details

    def _fetch_uta_history(
        self, method: str, since: int | None, until: int | None, *, kind: str
    ) -> list[dict[str, Any]]:
        now = int(time.time() * 1000)
        until = now if until is None else until
        since = now - _HISTORY_WINDOW_MS if since is None else since
        if since < now - _HISTORY_WINDOW_MS or until > now or since >= until:
            raise ValueError("UTA history must be within the last 90 days, ending at or before now")
        self._client.load_markets()
        out = []
        for start, end in _iter_time_windows(since, until, _UTA_HISTORY_WINDOW_MS):
            params: dict[str, Any] = {
                "category": self._history_product_type,
                "startTime": start,
                "endTime": end - 1 if end < until else end,
                "limit": 100,
            }
            seen_cursors: set[str] = set()
            while True:
                data = self._bitget_read(method, params)
                rows = data.get("list")
                if not isinstance(rows, list):
                    raise RuntimeError("Invalid UTA history page; import is incomplete")
                for row in rows:
                    if not isinstance(row, dict) or not row.get("symbol"):
                        raise RuntimeError("Invalid UTA history record; import is incomplete")
                    if row.get("category") != self._history_product_type:
                        raise RuntimeError("UTA history category mismatch; import is incomplete")
                    record_id = row.get("execId") or row.get("tradeId") if kind == "trade" else row.get("positionId") if kind == "position" else row.get("orderId")
                    if not record_id or (kind == "trade" and not row.get("orderId")):
                        raise RuntimeError("UTA history identifier missing; import is incomplete")
                    market = self._client.safe_market(row["symbol"], None, None, "contract")
                    out.append({"info": row, "symbol": market["symbol"]})
                cursor = str(data.get("cursor") or "")
                if not rows or not cursor:
                    break
                if cursor in seen_cursors:
                    raise RuntimeError("Repeated UTA history cursor; import is incomplete")
                seen_cursors.add(cursor)
                params["cursor"] = cursor
        return _deduplicate_history_rows(out, kind=kind)

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        if not symbols:
            return {}

        normalized = [s for s in symbols if s]
        if not normalized:
            return {}

        out: dict[str, float] = {}
        has_tickers = bool(getattr(self._client, "has", {}).get("fetchTickers"))
        if has_tickers:
            try:
                params = self._fetch_params()
                raw = call_with_retry(
                    lambda: self._client.fetch_tickers(normalized, params),
                    label=f"{self.exchange_name}.fetch_tickers",
                )
                batch_prices = self._parse_ticker_prices(raw or {}, normalized)
                if not self._uta or len(batch_prices) == len(normalized):
                    return batch_prices
                out.update(batch_prices)
                normalized = [symbol for symbol in normalized if symbol not in batch_prices]
            except Exception as exc:
                _logger.debug(
                    "%s fetch_tickers batch failed, falling back: %s",
                    self.exchange_name,
                    exc,
                )

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
        if self._uta:
            return self._fetch_uta_history(
                "privateUtaGetV3PositionHistoryPosition", since, until, kind="position"
            )
        if not getattr(self._client, "has", {}).get("fetchPositionsHistory"):
            return []

        out: list[dict[str, Any]] = []
        for window_since, window_until in _iter_time_windows(since, until):
            params = dict(self._fetch_params())
            params["paginate"] = True
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
        return _deduplicate_history_rows(out, kind="order")

    def fetch_closed_orders_history(
        self,
        *,
        since: Optional[int] = None,
        until: Optional[int] = None,
        symbols: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        if self._uta:
            return self._fetch_uta_history(
                "privateUtaGetV3TradeHistoryOrders", since, until, kind="order"
            )
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
                # CCXT's built-in paginator follows Bitget's cursor until the
                # endpoint is exhausted.  The surrounding time windows still
                # protect the exchange's maximum 90-day range.
                params["paginate"] = True
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
        return _deduplicate_history_rows(out, kind="order")

    def fetch_my_trades_history(
        self,
        *,
        since: Optional[int] = None,
        until: Optional[int] = None,
        symbols: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        if self._uta:
            return self._fetch_uta_history(
                "privateUtaGetV3TradeFills", since, until, kind="trade"
            )
        if not getattr(self._client, "has", {}).get("fetchMyTrades"):
            return []

        target_symbols: list[Optional[str]] = list(symbols) if symbols else [None]

        out: list[dict[str, Any]] = []
        for symbol in target_symbols:
            for window_since, window_until in _iter_time_windows(since, until):
                params = dict(self._fetch_params())
                params["paginate"] = True
                if window_until is not None:
                    params["until"] = window_until
                try:
                    batch = call_with_retry(
                        lambda sym=symbol, s=window_since, p=params: self._client.fetch_my_trades(
                            sym, s, None, p
                        ),
                        label=f"{self.exchange_name}.fetch_my_trades[{symbol}]",
                    )
                except Exception as exc:
                    _logger.warning(
                        "%s fetch_my_trades symbol=%s window skipped: %s",
                        self.exchange_name,
                        symbol,
                        exc,
                    )
                    continue
                out.extend(batch or [])
        return _deduplicate_history_rows(out, kind="trade")

    def fetch_order(
        self,
        order_id: str,
        *,
        symbol: str,
    ) -> Optional[dict[str, Any]]:
        if not getattr(self._client, "has", {}).get("fetchOrder"):
            return None
        params = self._fetch_params()
        try:
            return call_with_retry(
                lambda: self._client.fetch_order(order_id, symbol, params),
                label=f"{self.exchange_name}.fetch_order[{order_id}]",
            )
        except Exception as exc:
            _logger.debug(
                "%s fetch_order id=%s symbol=%s skipped: %s",
                self.exchange_name,
                order_id,
                symbol,
                exc,
            )
            return None

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
