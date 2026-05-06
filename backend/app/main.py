"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import (
    routes_accounts,
    routes_health,
    routes_manual,
    routes_overview,
    routes_pnl,
    routes_positions,
    routes_snapshots,
    routes_symbols,
)
from .core.config import get_settings
from .core.logging import get_logger, setup_logging
from .core.scheduler import shutdown_scheduler, start_scheduler
from .db.session import init_db

_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    settings = get_settings()
    if settings.posihub_encryption_key:
        start_scheduler()
    else:
        _logger.warning(
            "POSIHUB_ENCRYPTION_KEY not set - scheduler disabled until configured"
        )
    try:
        yield
    finally:
        shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="posihub backend",
        version=__version__,
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_health.router)
    app.include_router(routes_overview.router)
    app.include_router(routes_accounts.router)
    app.include_router(routes_positions.router)
    app.include_router(routes_pnl.router)
    app.include_router(routes_snapshots.router)
    app.include_router(routes_manual.router)
    app.include_router(routes_symbols.router)

    return app


app = create_app()
