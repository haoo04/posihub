"""Tests for exchange API connection probes and live market prices."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlmodel import select

from app.api import routes_accounts
from app.core.security import encrypt_secret
from app.db.models import (
    Account,
    AccountType,
    Exchange,
    ExchangeConnectionState,
    PositionCurrent,
    PositionSide,
)
from app.services.exchange.base import ExchangeClient, RawBalance, RawMarket, RawPosition
from app.services.live_prices import fetch_live_position_prices


@dataclass
class ProbeClient(ExchangeClient):
    exchange_name: str = "binance"
    closed: bool = False
    should_fail: bool = False

    def fetch_balance(self) -> list[RawBalance]:
        if self.should_fail:
            raise RuntimeError("invalid secret")
        return []

    def fetch_positions(self) -> list[RawPosition]:
        return []

    def fetch_markets(self) -> list[RawMarket]:
        return []

    def close(self) -> None:
        self.closed = True


def _exchange_and_account(session) -> tuple[Exchange, Account]:
    exchange = Exchange(name="binance", enabled=True)
    session.add(exchange)
    session.commit()
    session.refresh(exchange)
    account = Account(
        exchange_id=exchange.id,
        account_name="main",
        account_type=AccountType.SPOT,
        api_key_enc=encrypt_secret("key"),
        api_secret_enc=encrypt_secret("secret"),
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return exchange, account


def test_connection_test_persists_success_and_closes_client(
    in_memory_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange, account = _exchange_and_account(in_memory_session)
    client = ProbeClient()
    monkeypatch.setattr(routes_accounts, "build_client_for_account", lambda *_: client)

    result = routes_accounts.test_exchange_connection(account.id or 0, in_memory_session)

    assert result.exchange_name == exchange.name
    assert result.status == "connected"
    assert result.last_test_at is not None
    assert result.latency_ms is not None
    assert client.closed is True
    state = in_memory_session.exec(
        select(ExchangeConnectionState).where(
            ExchangeConnectionState.account_id == account.id
        )
    ).one()
    assert state.status == "connected"
    listed = routes_accounts.list_exchange_connections(in_memory_session)
    assert listed[0].status == "connected"


def test_connection_test_records_failure_without_leaking_secret(
    in_memory_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, account = _exchange_and_account(in_memory_session)
    client = ProbeClient(should_fail=True)
    monkeypatch.setattr(routes_accounts, "build_client_for_account", lambda *_: client)

    result = routes_accounts.test_exchange_connection(account.id or 0, in_memory_session)

    assert result.status == "error"
    assert "secret" not in (result.message or "")
    assert "***" in (result.message or "")


class PublicPriceClient:
    calls: list[list[str]] = []

    def __init__(self, exchange_id: str, **_: object) -> None:
        self.exchange_id = exchange_id

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        self.calls.append(symbols)
        return {"BTC/USDT": 51_000.0}

    def close(self) -> None:
        return None


def test_live_prices_batch_by_exchange_and_supports_merged_view(
    in_memory_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange = Exchange(name="binance", enabled=True)
    in_memory_session.add(exchange)
    in_memory_session.commit()
    in_memory_session.refresh(exchange)
    account = Account(
        exchange_id=exchange.id,
        account_name="spot-main",
        account_type=AccountType.SPOT,
        is_simulated=True,
    )
    in_memory_session.add(account)
    in_memory_session.commit()
    in_memory_session.refresh(account)
    in_memory_session.add(
        PositionCurrent(
            account_id=account.id or 0,
            canonical_symbol="BTC-USDT-SPOT",
            side=PositionSide.LONG,
            qty=2.0,
            mark_price=50_000.0,
        )
    )
    in_memory_session.commit()
    PublicPriceClient.calls = []
    monkeypatch.setattr("app.services.live_prices.CcxtExchangeClient", PublicPriceClient)

    split = fetch_live_position_prices(
        in_memory_session, view="split", market="spot"
    )
    merged = fetch_live_position_prices(
        in_memory_session, view="merged", market="spot"
    )

    assert split.prices[0].price == 51_000.0
    assert split.prices[0].position_id is not None
    assert merged.prices[0].canonical_symbol == "BTC-USDT-SPOT"
    assert merged.prices[0].price == 51_000.0
    assert all(call == ["BTC/USDT"] for call in PublicPriceClient.calls)
