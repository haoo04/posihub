"""Application logging setup.

Provides a single :func:`setup_logging` entry point and a small helper to
prevent secrets from being printed accidentally.
"""

from __future__ import annotations

import logging
import sys
from logging import Logger


_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Initialise root logger with a simple console handler (idempotent)."""

    root = logging.getLogger()
    if getattr(root, "_posihub_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for noisy in ("ccxt.base.exchange", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._posihub_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> Logger:
    return logging.getLogger(name)
