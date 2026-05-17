"""Application configuration using pydantic-settings.

Loads values from environment variables and an optional `.env` file located
at the project root. All values are immutable after the first instantiation
(via :func:`get_settings`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"


def _default_database_url() -> str:
    path = (BACKEND_ROOT / "posihub.db").resolve()
    return f"sqlite:///{path.as_posix()}"


def _resolve_sqlite_database_url(url: str) -> str:
    """Resolve relative SQLite paths against ``backend/``, not the shell cwd."""

    if not url.startswith("sqlite") or ":///" not in url:
        return url

    scheme, path = url.split(":///", 1)
    if path == ":memory:" or path.startswith(":memory:"):
        return url

    db_path = Path(path)
    if db_path.is_absolute():
        return url

    resolved = (BACKEND_ROOT / db_path).resolve()
    return f"{scheme}:///{resolved.as_posix()}"


class Settings(BaseSettings):
    """Runtime settings for the posihub backend."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="posihub")
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    app_debug: bool = Field(default=True)
    app_timezone: str = Field(default="Asia/Shanghai")

    database_url: str = Field(default_factory=_default_database_url)

    posihub_encryption_key: str | None = Field(default=None)

    sync_interval_minutes: int = Field(default=5, ge=1, le=120)
    sync_max_workers: int = Field(default=4, ge=1, le=32)
    daily_snapshot_time: str = Field(default="23:55")

    cors_allow_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173"
    )

    # Feature flags
    enable_position_order_edit: bool = Field(default=True)

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return _resolve_sqlite_database_url(value)

    @field_validator("daily_snapshot_time")
    @classmethod
    def _validate_daily_snapshot_time(cls, value: str) -> str:
        try:
            hour_str, minute_str = value.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except ValueError as exc:
            raise ValueError("daily_snapshot_time must be HH:MM") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("daily_snapshot_time out of range")
        return f"{hour:02d}:{minute:02d}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]

    @property
    def daily_snapshot_hour_minute(self) -> tuple[int, int]:
        hour_str, minute_str = self.daily_snapshot_time.split(":")
        return int(hour_str), int(minute_str)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""

    return Settings()
