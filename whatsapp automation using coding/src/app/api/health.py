"""
health.py — Health-check API router.

The /health endpoint:
  - Returns 200 OK when the application is running.
  - Reports which optional config groups are configured vs. missing.
  - NEVER reveals credential values — only their variable names.

This endpoint requires NO external API keys or network calls.
It is safe to call at any time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


class ModuleStatus(BaseModel):
    configured: bool
    missing_vars: list[str]


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str
    timestamp: str
    modules: dict[str, ModuleStatus]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns application health. "
        "Shows which configuration groups are ready without exposing secret values."
    ),
)
def health_check() -> HealthResponse:
    """Return application health and configuration readiness."""
    logger.info("Health check requested")

    m2_missing = settings.missing_module2_vars()
    m3_missing = settings.missing_module3_vars()
    m4_missing = settings.missing_module4_vars()

    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
        timestamp=datetime.now(timezone.utc).isoformat(),
        modules={
            "whatsapp": ModuleStatus(
                configured=len(m2_missing) == 0,
                missing_vars=m2_missing,
            ),
            "google_sheets": ModuleStatus(
                configured=len(m3_missing) == 0,
                missing_vars=m3_missing,
            ),
            "llm": ModuleStatus(
                configured=len(m4_missing) == 0,
                missing_vars=m4_missing,
            ),
        },
    )
