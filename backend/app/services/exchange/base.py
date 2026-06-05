"""Exchange connector interfaces.

Defines the dataclasses returned by every exchange adapter and the abstract
base class that adapters must implement. Higher layers (normalisation,
aggregation, repositories) only depend on these neutral structures, never on
CCXT directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class RawBalance:
    asset: str
    equity: float
    available: float
    frozen: float


@dataclass(slots=True)
class RawPosition:
    raw_symbol: str
    side: str  # "long" / "short" / "net"
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float = 1.0
    margin_mode: Optional[str] = None
    contract_size: float = 1.0


@dataclass(slots=True)
class RawMarket:
    raw_symbol: str
    base_asset: str
    quote_asset: str
    instrument_type: str  # "spot" / "perp" / "futures"
    contract_size: float = 1.0


@dataclass(slots=True)
class FetchResult:
    balances: list[RawBalance] = field(default_factory=list)
    positions: list[RawPosition] = field(default_factory=list)


class ExchangeClient(ABC):
    """Abstract read-only exchange connector."""

    exchange_name: str

    @abstractmethod
    def fetch_balance(self) -> list[RawBalance]:
        """Return per-asset balances."""

    @abstractmethod
    def fetch_positions(self) -> list[RawPosition]:
        """Return open derivative positions (empty list for spot accounts)."""

    @abstractmethod
    def fetch_markets(self) -> list[RawMarket]:
        """Return market metadata used for symbol mapping."""

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        """Return last/mark prices for CCXT-style symbols (e.g. ``BTC/USDT``)."""

        return {}

    def fetch_closed_orders_history(
        self,
        *,
        since: Optional[int] = None,
        until: Optional[int] = None,
        symbols: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Return raw filled/closed order dicts in ``[since, until]`` (ms).

        Default no-op; only connectors that support order history override
        this. Returned dicts are exchange-native CCXT order structures so the
        per-exchange normalisation layer can read raw fields.
        """

        return []

    def fetch_positions_history(
        self,
        *,
        since: Optional[int] = None,
        until: Optional[int] = None,
        symbols: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Return raw closed-position dicts in ``[since, until]`` (ms).

        Default no-op; overridden by connectors that expose a positions
        history endpoint. Used for import validation, not as the source of
        truth for the order ledger.
        """

        return []

    def fetch_all(self) -> FetchResult:
        """Convenience helper combining balance + positions."""

        return FetchResult(
            balances=self.fetch_balance(),
            positions=self.fetch_positions(),
        )

    def close(self) -> None:  # pragma: no cover - default no-op
        """Release any underlying network resources."""
