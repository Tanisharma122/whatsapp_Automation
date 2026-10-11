"""
main.py — FastAPI application entry point.

This file creates the FastAPI app, configures logging, registers routers,
and performs a startup check for missing configuration variables.

Run locally with:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.config import settings
from app.logging_config import setup_logging
from app.api.health import router as health_router
from app.api.webhook import router as webhook_router

# ── Logging must be configured before any other imports that log ───────────────
setup_logging(
    log_level=settings.log_level.value,
    pretty=settings.is_development(),
)

logger = logging.getLogger(__name__)


# ── Startup / shutdown lifecycle ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """
    Code inside the `async with` block runs at startup.
    Code after `yield` runs at shutdown.
    """
    logger.info("Starting %s v%s [%s]", settings.app_name, settings.app_version, settings.app_env.value)

    # --- Startup configuration check -------------------------------------------
    # We report WHICH variables are missing, not their values.
    m2 = settings.missing_module2_vars()
    m3 = settings.missing_module3_vars()
    m4 = settings.missing_module4_vars()

    if m2:
        logger.warning("Module 2 (WhatsApp) — missing config vars: %s", m2)
    if m3:
        logger.warning("Module 3 (Google Sheets) — missing config vars: %s", m3)
    if m4:
        logger.warning("Module 4 (LLM) — missing config vars: %s", m4)

    if not any([m2, m3, m4]):
        logger.info("All configuration groups are fully configured.")
    else:
        logger.info(
            "Application started. Some modules are not yet configured — "
            "this is expected during Module 1 development."
        )

    yield  # ← application is running here

    logger.info("Shutting down %s", settings.app_name)


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "WhatsApp Food Delivery AI Agent — "
        "Receives customer messages, understands intent using an LLM, "
        "reads live inventory from Google Sheets, and confirms orders."
    ),
    lifespan=lifespan,
    # In production we'd disable the docs; fine to leave on for development
    docs_url="/docs" if settings.is_development() else None,
    redoc_url="/redoc" if settings.is_development() else None,
)

# ── Register routers ───────────────────────────────────────────────────────────
app.include_router(health_router)

app.include_router(webhook_router)   # Module 2

# More routers will be added in later modules:
# app.include_router(orders_router)    # Module 3+
