"""Tests for account-type branching in sync_service."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.db.models import Account, AccountType, Exchange
from app.services.exchange.base import ExchangeClient, RawBalance, RawMarket, RawPosition
from app.services.sync_service import sync_account


@dataclass
class RecordingClient(ExchangeClient):
    exchange_name: str = "binance"
    fetch_positions_calls: int = 0
    fetch_last_prices_calls: int = 0
    prices: dict[str, float] = field(default_factory=lambda: {"BTC/USDT": 50_000.0})

    def fetch_balance(self) -> list[RawBalance]:
        return [
            RawBalance(asset="USDT", equity=1_000.0, available=1_000.0, frozen=0.0),
            RawBalance(asset="BTC", equity=0.1, available=0.1, frozen=0.0),
        ]

    def fetch_positions(self) -> list[RawPosition]:
        self.fetch_positions_calls += 1
        return [
            RawPosition(
                raw_symbol="BTC/USDT:USDT",
                side="long",
                qty=1.0,
                entry_price=30_000.0,
                mark_price=31_000.0,
                unrealized_pnl=1_000.0,
            )
        ]

    def fetch_markets(self) -> list[RawMarket]:
        return []

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        self.fetch_last_prices_calls += 1
        return {s: self.prices[s] for s in symbols if s in self.prices}


def _seed_exchange(session) -> Exchange:
    exch = Exchange(name="binance", enabled=True)
    session.add(exch)
    session.commit()
    session.refresh(exch)
    return exch


def test_sync_spot_derives_positions_not_fetch_positions(
    in_memory_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    exch = _seed_exchange(in_memory_session)
    client = RecordingClient()
    account = Account(
        exchange_id=exch.id,
        account_name="spot-main",
        account_type=AccountType.SPOT,
        enabled=True,
    )
    in_memory_session.add(account)
    in_memory_session.commit()
    in_memory_session.refresh(account)

    monkeypatch.setattr(
        "app.services.sync_service.build_client_for_account",
        lambda _session, _account: client,
    )

    outcome = sync_account(in_memory_session, account)
    in_memory_session.commit()

    assert outcome.success is True
    assert outcome.position_count == 1
    assert client.fetch_positions_calls == 0
    assert client.fetch_last_prices_calls == 1


def test_sync_perp_fetches_positions_not_spot_deriver(
    in_memory_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    exch = _seed_exchange(in_memory_session)
    client = RecordingClient()
    account = Account(
        exchange_id=exch.id,
        account_name="perp-main",
        account_type=AccountType.USDT_PERP,
        enabled=True,
    )
    in_memory_session.add(account)
    in_memory_session.commit()
    in_memory_session.refresh(account)

    monkeypatch.setattr(
        "app.services.sync_service.build_client_for_account",
        lambda _session, _account: client,
    )

    outcome = sync_account(in_memory_session, account)
    in_memory_session.commit()

    assert outcome.success is True
    assert client.fetch_positions_calls == 1
    assert client.fetch_last_prices_calls == 0


def test_sync_funding_has_no_positions(
    in_memory_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    exch = _seed_exchange(in_memory_session)
    client = RecordingClient()
    account = Account(
        exchange_id=exch.id,
        account_name="funding",
        account_type=AccountType.FUNDING,
        enabled=True,
    )
    in_memory_session.add(account)
    in_memory_session.commit()
    in_memory_session.refresh(account)

    monkeypatch.setattr(
        "app.services.sync_service.build_client_for_account",
        lambda _session, _account: client,
    )

    outcome = sync_account(in_memory_session, account)
    in_memory_session.commit()

    assert outcome.success is True
    assert outcome.position_count == 0
    assert client.fetch_positions_calls == 0
    assert client.fetch_last_prices_calls == 0
