"""Exponential-backoff retry helper for exchange calls."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

from ...core.logging import get_logger

T = TypeVar("T")

_logger = get_logger(__name__)


# Errors that should be retried. Imported lazily to keep ccxt optional at
# import time (some unit tests exercise the helper without network access).
_RETRY_ERRORS: tuple[type[BaseException], ...] | None = None


def _retry_errors() -> tuple[type[BaseException], ...]:
    global _RETRY_ERRORS
    if _RETRY_ERRORS is not None:
        return _RETRY_ERRORS
    try:
        import ccxt  # type: ignore

        _RETRY_ERRORS = (
            ccxt.NetworkError,
            ccxt.ExchangeNotAvailable,
            ccxt.RequestTimeout,
            ccxt.RateLimitExceeded,
            ccxt.DDoSProtection,
        )
    except Exception:  # pragma: no cover - ccxt always installed in prod
        _RETRY_ERRORS = (TimeoutError, ConnectionError)
    return _RETRY_ERRORS


def call_with_retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    label: str = "exchange",
) -> T:
    """Invoke ``func`` with exponential backoff on transient errors."""

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except _retry_errors() as exc:
            last_exc = exc
            if attempt >= attempts:
                _logger.error(
                    "%s call failed after %d attempts: %s", label, attempt, exc
                )
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, base_delay)
            _logger.warning(
                "%s call failed (attempt %d/%d): %s. retry in %.2fs",
                label,
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None  # pragma: no cover
    raise last_exc
