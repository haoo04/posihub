"""End-to-end tests for the symbol-mapping REST endpoints.

Covers the Phase 2 conflict-resolution surface:
- ``POST /api/v1/symbols`` still rejects duplicate ``(exchange, raw_symbol)``.
- ``POST /api/v1/symbols/upsert`` is idempotent on that key.
- ``PATCH /api/v1/symbols/{id}`` performs partial updates.

We drive the tests through a single :class:`TestClient` context manager so
the FastAPI lifespan runs ``init_db()`` once on the shared engine.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    # SQLite ``:memory:`` databases are per-connection by default, so the
    # default ``QueuePool`` would give each request a fresh empty DB and the
    # tables created during ``init_db`` would be invisible to subsequent
    # connections. ``StaticPool`` pins the engine to a single underlying
    # connection so the schema persists across requests.
    from app.db import session as db_session

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_engine = db_session.engine
    db_session.engine = test_engine

    from app.main import create_app

    try:
        with TestClient(create_app()) as instance:
            yield instance
    finally:
        db_session.engine = original_engine


def _payload(raw: str, canonical: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "exchange": "binance",
        "raw_symbol": raw,
        "canonical_symbol": canonical,
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "instrument_type": "perp",
        "contract_size": 1.0,
        "is_active": True,
    }
    body.update(overrides)
    return body


def test_create_then_duplicate_returns_409(client: TestClient) -> None:
    first = client.post("/api/v1/symbols", json=_payload("DUP_RAW_1", "BTC-USDT-PERP"))
    assert first.status_code == 201

    second = client.post("/api/v1/symbols", json=_payload("DUP_RAW_1", "BTC-USDT-PERP"))
    assert second.status_code == 409


def test_upsert_creates_then_updates_same_row(client: TestClient) -> None:
    created = client.post(
        "/api/v1/symbols/upsert",
        json=_payload("UPSERT_RAW_1", "BTC-USDT-PERP"),
    )
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["canonical_symbol"] == "BTC-USDT-PERP"
    row_id = created_body["id"]

    updated = client.post(
        "/api/v1/symbols/upsert",
        json=_payload("UPSERT_RAW_1", "BTC-USD-PERP", base_asset="BTC", quote_asset="USD"),
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["id"] == row_id
    assert updated_body["canonical_symbol"] == "BTC-USD-PERP"
    assert updated_body["quote_asset"] == "USD"


def test_patch_partial_update(client: TestClient) -> None:
    created = client.post(
        "/api/v1/symbols",
        json=_payload("PATCH_RAW_1", "BTC-USDT-PERP"),
    )
    assert created.status_code == 201
    row_id = created.json()["id"]

    patched = client.patch(
        f"/api/v1/symbols/{row_id}",
        json={"is_active": False, "canonical_symbol": "BTC-USDT-SPOT"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["is_active"] is False
    assert body["canonical_symbol"] == "BTC-USDT-SPOT"
    assert body["quote_asset"] == "USDT"


def test_patch_unknown_id_returns_404(client: TestClient) -> None:
    response = client.patch("/api/v1/symbols/9999999", json={"is_active": False})
    assert response.status_code == 404
