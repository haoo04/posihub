"""Exchange connector interfaces.

Defines the dataclasses returned by every exchange adapter and the abstract
base class that adapters must implement. Higher layers (normalisation,
aggregation, repositories) only depend on these neutral structures, never on
CCXT directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


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

    def fetch_all(self) -> FetchResult:
        """Convenience helper combining balance + positions."""

        return FetchResult(
            balances=self.fetch_balance(),
            positions=self.fetch_positions(),
        )

    def close(self) -> None:  # pragma: no cover - default no-op
        """Release any underlying network resources."""
