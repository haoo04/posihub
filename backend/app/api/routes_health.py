"""Health and metadata endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..core.config import get_settings
from ..schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app=settings.app_name, version=__version__)
