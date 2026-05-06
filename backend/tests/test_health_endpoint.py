"""Smoke test that wires FastAPI through TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok() -> None:
    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]
    assert body["version"]
