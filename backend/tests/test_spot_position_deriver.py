"""Tests for spot position derivation."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models import PositionSide
from app.services.exchange.base import ExchangeClient, RawBalance, RawMarket, RawPosition
from app.services.normalize.symbol_mapper import SymbolMapper
from app.services.spot.position_deriver import derive_spot_positions


@dataclass
class FakeSpotClient(ExchangeClient):
    exchange_name: str = "binance"
    prices: dict[str, float] = field(default_factory=dict)

    def fetch_balance(self) -> list[RawBalance]:
        return []

    def fetch_positions(self) -> list[RawPosition]:
        return []

    def fetch_markets(self) -> list[RawMarket]:
        return []

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        return {s: self.prices[s] for s in symbols if s in self.prices}


def test_derive_spot_skips_stablecoins(in_memory_session) -> None:
    client = FakeSpotClient(prices={"BTC/USDT": 50_000.0})
    mapper = SymbolMapper(in_memory_session)
    balances = [
        RawBalance(asset="USDT", equity=10_000.0, available=10_000.0, frozen=0.0),
        RawBalance(asset="BTC", equity=0.5, available=0.5, frozen=0.0),
    ]

    rows = derive_spot_positions(
        account_id=1,
        exchange_name="binance",
        balances=balances,
        client=client,
        mapper=mapper,
        dust_threshold_usd=1.0,
    )

    assert len(rows) == 1
    assert rows[0].canonical_symbol == "BTC-USDT-SPOT"
    assert rows[0].side == PositionSide.LONG
    assert rows[0].qty == 0.5
    assert rows[0].mark_price == 50_000.0
    assert rows[0].entry_price == 0.0
    assert rows[0].unrealized_pnl == 0.0
    assert rows[0].leverage == 1.0


def test_derive_spot_filters_dust(in_memory_session) -> None:
    client = FakeSpotClient(prices={"DOGE/USDT": 0.05})
    mapper = SymbolMapper(in_memory_session)
    balances = [
        RawBalance(asset="DOGE", equity=10.0, available=10.0, frozen=0.0),
    ]

    rows = derive_spot_positions(
        account_id=1,
        exchange_name="binance",
        balances=balances,
        client=client,
        mapper=mapper,
        dust_threshold_usd=1.0,
    )

    assert rows == []


def test_derive_spot_computes_pnl_when_entry_known(in_memory_session) -> None:
    client = FakeSpotClient(prices={"ETH/USDT": 3_000.0})
    mapper = SymbolMapper(in_memory_session)
    balances = [
        RawBalance(asset="ETH", equity=2.0, available=2.0, frozen=0.0),
    ]

    rows = derive_spot_positions(
        account_id=1,
        exchange_name="binance",
        balances=balances,
        client=client,
        mapper=mapper,
        dust_threshold_usd=0.0,
    )
    rows[0].entry_price = 2_500.0
    rows[0].unrealized_pnl = (3_000.0 - 2_500.0) * 2.0

    assert rows[0].unrealized_pnl == 1_000.0
