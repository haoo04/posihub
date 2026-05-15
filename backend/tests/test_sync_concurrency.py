"""Concurrency tests for :func:`sync_all_accounts`.

We don't exercise the real CCXT path here. The test substitutes both the
account discovery and the per-account worker, then asserts the orchestrator:

1. Submits every active account to the thread pool.
2. Runs them concurrently (wall-clock close to a single worker, not the sum).
3. Returns one :class:`SyncOutcome` per account, isolating failures.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import sync_service
from app.services.sync_service import SyncOutcome, sync_all_accounts


def _fake_accounts(ids: list[int]) -> list[Any]:
    return [SimpleNamespace(id=i, enabled=True) for i in ids]


def test_sync_all_accounts_runs_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    account_ids = [1, 2, 3, 4]
    monkeypatch.setattr(
        sync_service,
        "list_active_accounts",
        lambda _session: _fake_accounts(account_ids),
    )

    sleep_duration = 0.25
    active = {"count": 0, "peak": 0}
    lock = threading.Lock()

    def fake_worker(account_id: int) -> SyncOutcome:
        with lock:
            active["count"] += 1
            active["peak"] = max(active["peak"], active["count"])
        time.sleep(sleep_duration)
        with lock:
            active["count"] -= 1
        return SyncOutcome(
            account_id=account_id,
            success=True,
            message="ok",
        )

    monkeypatch.setattr(sync_service, "_sync_one_committed", fake_worker)

    started = time.perf_counter()
    outcomes = sync_all_accounts(max_workers=4)
    elapsed = time.perf_counter() - started

    assert {o.account_id for o in outcomes} == set(account_ids)
    assert all(o.success for o in outcomes)
    # Peak concurrency must exceed 1 to prove the pool is in use.
    assert active["peak"] >= 2
    # Wall-clock must be far below sequential (4 * sleep_duration).
    assert elapsed < sleep_duration * len(account_ids) * 0.8


def test_sync_all_accounts_isolates_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    account_ids = [10, 11, 12]
    monkeypatch.setattr(
        sync_service,
        "list_active_accounts",
        lambda _session: _fake_accounts(account_ids),
    )

    def fake_worker(account_id: int) -> SyncOutcome:
        if account_id == 11:
            return SyncOutcome(
                account_id=account_id,
                success=False,
                message="boom",
            )
        return SyncOutcome(account_id=account_id, success=True, message="ok")

    monkeypatch.setattr(sync_service, "_sync_one_committed", fake_worker)

    outcomes = {o.account_id: o for o in sync_all_accounts(max_workers=3)}
    assert outcomes[10].success is True
    assert outcomes[11].success is False
    assert outcomes[12].success is True


def test_sync_all_accounts_no_accounts_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sync_service, "list_active_accounts", lambda _session: []
    )
    assert sync_all_accounts() == []
