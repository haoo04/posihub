"""Shared pytest fixtures."""

from __future__ import annotations

import os

# Use a throwaway in-memory SQLite db and a deterministic encryption key for
# every test run. Setting these *before* the application is imported makes
# `get_settings` pick them up.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault(
    "POSIHUB_ENCRYPTION_KEY", "FfL0gOCOl7WvPQNyaDUH1uORqDcNVFc-_lP4U8vUx0M="
)
os.environ.setdefault("APP_DEBUG", "true")

import pytest  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402


@pytest.fixture()
def in_memory_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Importing models registers them with SQLModel.metadata.
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
