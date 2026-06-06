"""Tests for performance metrics services and API."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.models import (
    Account,
    AccountSnapshotDaily,
    AccountType,
    DataSource,
    Exchange,
    PositionCurrent,
    PositionOrder,
    PositionOrderStatus,
    PositionSide,
)
from app.services.performance.breakdown import (
    compute_breakdown,
    compute_realized_series,
)
from app.services.performance.equity_metrics import (
    annualized_return,
    compute_equity_metrics,
    drawdown_pct_series,
    max_drawdown_pct,
)
from app.services.performance.scope import resolve_performance_scope
from app.services.performance.trade_metrics import _streaks, compute_trade_metrics
from app.services.position_order_close import fifo_close_position

_seed_counter = 0


def _seed_exchange_account(session: Session, *, simulated: bool = False) -> Account:
    global _seed_counter
    _seed_counter += 1
    exchange = Exchange(name=f"ex-perf-{_seed_counter}")
    session.add(exchange)
    session.flush()
    account = Account(
        exchange_id=exchange.id,
        account_name=f"acct-perf-{_seed_counter}",
        account_type=AccountType.USDT_PERP,
        is_simulated=simulated,
    )
    session.add(account)
    session.flush()
    return account


def _seed_second_account(session: Session, exchange_id: int) -> Account:
    global _seed_counter
    _seed_counter += 1
    account = Account(
        exchange_id=exchange_id,
        account_name=f"acct-perf-{_seed_counter}",
        account_type=AccountType.USDT_PERP,
    )
    session.add(account)
    session.flush()
    return account


def test_drawdown_monotonic_up_is_zero() -> None:
    assert max_drawdown_pct([100.0, 110.0, 120.0]) == pytest.approx(0.0)


def test_drawdown_peak_to_trough() -> None:
    equities = [100.0, 120.0, 90.0, 95.0]
    assert max_drawdown_pct(equities) == pytest.approx(0.25)
    series = drawdown_pct_series(equities)
    assert series[2] == pytest.approx(0.25)


def test_streaks_basic() -> None:
    # W W L L L W  -> max win 2, max loss 3
    pnls = [10.0, 5.0, -1.0, -2.0, -3.0, 4.0]
    assert _streaks(pnls) == (2, 3)


def test_streaks_breakeven_resets() -> None:
    pnls = [10.0, 0.0, 10.0]
    assert _streaks(pnls) == (1, 0)


def test_annualized_return_doubles_in_half_year() -> None:
    # +100% over ~182.5 days annualizes to +300% (compounded x4 over the year)
    result = annualized_return(1.0, 365 // 2)
    assert result == pytest.approx(3.0, rel=1e-2)


def test_annualized_return_zero_span() -> None:
    assert annualized_return(0.5, 0) == pytest.approx(0.0)


def test_equity_metrics_multi_account_sum(in_memory_session: Session) -> None:
    a1 = _seed_exchange_account(in_memory_session)
    a2 = _seed_second_account(in_memory_session, int(a1.exchange_id))
    today = date.today()
    yesterday = today - timedelta(days=1)

    for snap_date, a1_eq, a2_eq in [
        (yesterday, 1000.0, 500.0),
        (today, 1100.0, 550.0),
    ]:
        in_memory_session.add(
            AccountSnapshotDaily(
                snapshot_date=snap_date,
                account_id=a1.id,
                asset="USDT",
                total_equity=a1_eq,
            )
        )
        in_memory_session.add(
            AccountSnapshotDaily(
                snapshot_date=snap_date,
                account_id=a2.id,
                asset="USDT",
                total_equity=a2_eq,
            )
        )
    in_memory_session.commit()

    scope = resolve_performance_scope(in_memory_session)
    metrics = compute_equity_metrics(
        in_memory_session,
        scope=scope,
        start_date=yesterday,
        end_date=today,
        asset="USDT",
    )

    assert metrics.equity_start == pytest.approx(1500.0)
    assert metrics.equity_end == pytest.approx(1650.0)
    assert metrics.equity_change == pytest.approx(150.0)
    assert metrics.equity_change_pct == pytest.approx(0.1)
    assert len(metrics.points) == 2


def test_equity_metrics_respects_account_scope(in_memory_session: Session) -> None:
    a1 = _seed_exchange_account(in_memory_session)
    a2 = _seed_second_account(in_memory_session, int(a1.exchange_id))
    today = date.today()

    in_memory_session.add(
        AccountSnapshotDaily(
            snapshot_date=today,
            account_id=a1.id,
            asset="USDT",
            total_equity=1000.0,
        )
    )
    in_memory_session.add(
        AccountSnapshotDaily(
            snapshot_date=today,
            account_id=a2.id,
            asset="USDT",
            total_equity=2000.0,
        )
    )
    in_memory_session.commit()

    scope = resolve_performance_scope(
        in_memory_session, account_ids=[int(a1.id)]
    )
    metrics = compute_equity_metrics(
        in_memory_session,
        scope=scope,
        start_date=today,
        end_date=today,
        asset="USDT",
    )
    assert metrics.equity_end == pytest.approx(1000.0)
    assert len(scope.account_ids) == 1


def _bootstrap_position(session: Session, account: Account) -> PositionCurrent:
    position = PositionCurrent(
        account_id=account.id,
        canonical_symbol="BTC-USDT-PERP",
        side=PositionSide.LONG,
        qty=1.0,
        entry_price=50_000.0,
        mark_price=52_000.0,
        source=DataSource.MANUAL,
    )
    session.add(position)
    session.flush()
    order = PositionOrder(
        position_id=position.id,
        source=DataSource.MANUAL,
        open_qty=1.0,
        remaining_qty=1.0,
        entry_price=50_000.0,
        status=PositionOrderStatus.OPEN,
    )
    session.add(order)
    session.flush()
    return position


def test_trade_metrics_win_rate_and_profit_factor(in_memory_session: Session) -> None:
    account = _seed_exchange_account(in_memory_session)
    position = _bootstrap_position(in_memory_session, account)

    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.5,
        close_price=52_000.0,
    )
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.5,
        close_price=48_000.0,
    )
    in_memory_session.commit()

    scope = resolve_performance_scope(in_memory_session)
    today = date.today()
    trade = compute_trade_metrics(
        in_memory_session,
        scope=scope,
        start_date=today - timedelta(days=1),
        end_date=today,
    )

    assert trade.trade_count == 2
    assert trade.win_count == 1
    assert trade.loss_count == 1
    assert trade.win_rate == pytest.approx(0.5)
    assert trade.realized_pnl_total == pytest.approx(0.0)
    assert trade.profit_factor == pytest.approx(1.0)
    assert trade.max_win_streak == 1
    assert trade.max_loss_streak == 1


def test_breakdown_by_symbol_and_side(in_memory_session: Session) -> None:
    account = _seed_exchange_account(in_memory_session)
    position = _bootstrap_position(in_memory_session, account)
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.5,
        close_price=52_000.0,
    )
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.5,
        close_price=48_000.0,
    )
    in_memory_session.commit()

    scope = resolve_performance_scope(in_memory_session)
    today = date.today()
    by_symbol = compute_breakdown(
        in_memory_session,
        scope=scope,
        dimension="symbol",
        start_date=today - timedelta(days=1),
        end_date=today,
    )
    assert len(by_symbol) == 1
    assert by_symbol[0].key == "BTC-USDT-PERP"
    assert by_symbol[0].trade_count == 2
    assert by_symbol[0].win_count == 1

    by_side = compute_breakdown(
        in_memory_session,
        scope=scope,
        dimension="side",
        start_date=today - timedelta(days=1),
        end_date=today,
    )
    assert by_side[0].key == "long"
    assert by_side[0].trade_count == 2


def test_realized_series_groups_by_day(in_memory_session: Session) -> None:
    account = _seed_exchange_account(in_memory_session)
    position = _bootstrap_position(in_memory_session, account)
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.5,
        close_price=52_000.0,
    )
    in_memory_session.commit()

    scope = resolve_performance_scope(in_memory_session)
    today = date.today()
    points = compute_realized_series(
        in_memory_session,
        scope=scope,
        start_date=today - timedelta(days=1),
        end_date=today,
    )
    assert len(points) == 1
    assert points[0].trade_count == 1
    assert points[0].realized_pnl == pytest.approx(1000.0)


@pytest.fixture()
def client_overridden_session(
    in_memory_session: Session,
) -> Iterator[TestClient]:
    from app.api.deps import get_session
    from app.main import create_app

    def override_get_session() -> Iterator[Session]:
        yield in_memory_session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_performance_summary_api(
    in_memory_session: Session,
    client_overridden_session: TestClient,
) -> None:
    account = _seed_exchange_account(in_memory_session)
    today = date.today()
    in_memory_session.add(
        AccountSnapshotDaily(
            snapshot_date=today,
            account_id=account.id,
            asset="USDT",
            total_equity=10_000.0,
        )
    )
    position = _bootstrap_position(in_memory_session, account)
    fifo_close_position(
        in_memory_session,
        position_id=position.id,
        close_qty=0.2,
        close_price=55_000.0,
    )
    in_memory_session.commit()

    resp = client_overridden_session.get(
        "/api/v1/performance/summary",
        params={"range": "7d", "account_ids": str(account.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["equity_end"] == pytest.approx(10_000.0)
    assert body["trade_count"] == 1
    assert body["win_count"] == 1
    assert body["realized_pnl_total"] == pytest.approx(1000.0)
    assert body["open_position_count"] == 1

    equity_resp = client_overridden_session.get(
        "/api/v1/performance/equity",
        params={"range": "7d", "account_ids": str(account.id)},
    )
    assert equity_resp.status_code == 200
    equity_body = equity_resp.json()
    assert len(equity_body["points"]) >= 1
    assert equity_body["points"][-1]["total_equity"] == pytest.approx(10_000.0)

    breakdown_resp = client_overridden_session.get(
        "/api/v1/performance/breakdown",
        params={"range": "7d", "dimension": "symbol", "account_ids": str(account.id)},
    )
    assert breakdown_resp.status_code == 200
    breakdown_body = breakdown_resp.json()
    assert breakdown_body["dimension"] == "symbol"
    assert breakdown_body["rows"][0]["key"] == "BTC-USDT-PERP"

    bad_dim = client_overridden_session.get(
        "/api/v1/performance/breakdown",
        params={"range": "7d", "dimension": "bogus"},
    )
    assert bad_dim.status_code == 400

    realized_resp = client_overridden_session.get(
        "/api/v1/performance/realized",
        params={"range": "7d", "account_ids": str(account.id)},
    )
    assert realized_resp.status_code == 200
    realized_body = realized_resp.json()
    assert len(realized_body["points"]) == 1
    assert realized_body["points"][0]["realized_pnl"] == pytest.approx(1000.0)
