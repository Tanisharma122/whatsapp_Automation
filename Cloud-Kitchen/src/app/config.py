"""
config.py — Typed application configuration using pydantic-settings.

All values are read from environment variables (or a .env file).
This module NEVER exposes secret values — only their names if missing.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Copy .env.example → .env and fill in the real values.
    Do NOT hardcode secrets here.
    """

    model_config = SettingsConfigDict(
        # Look for a .env file in the project root (parent of src/)
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Don't fail on extra env vars — other tools may set them
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────
    app_env: AppEnv = Field(default=AppEnv.DEVELOPMENT, description="Runtime environment")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging verbosity")
    app_name: str = Field(default="Cloud Kitchen WhatsApp AI Agent")
    app_version: str = Field(default="0.1.0")

    # ── WhatsApp (Module 2) ────────────────────────────────────
    whatsapp_access_token: Optional[str] = Field(default=None)
    whatsapp_phone_number_id: Optional[str] = Field(default=None)
    whatsapp_business_account_id: Optional[str] = Field(default=None)
    whatsapp_webhook_verify_token: Optional[str] = Field(default=None)
    # For development testing only — loaded from .env, never hardcoded
    test_recipient_phone: Optional[str] = Field(default=None)

    # ── LLM Provider (Module 4) ───────────────────────────────
    llm_provider: Optional[str] = Field(default=None)
    llm_api_key: Optional[str] = Field(default=None)
    llm_model: Optional[str] = Field(default=None)

    # ── Google Sheets (Module 3) ──────────────────────────────
    google_service_account_json_path: Optional[str] = Field(default=None)
    inventory_spreadsheet_id: Optional[str] = Field(default=None)
    inventory_worksheet_name: Optional[str] = Field(default="Sheet1")
    faq_spreadsheet_id: Optional[str] = Field(default=None)
    faq_worksheet_name: Optional[str] = Field(default="Sheet1")
    orders_spreadsheet_id: Optional[str] = Field(default=None)
    orders_worksheet_name: Optional[str] = Field(default="Orders")

    @field_validator("whatsapp_access_token", "llm_api_key", mode="before")
    @classmethod
    def _strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Strip accidental whitespace from credential values."""
        return v.strip() if isinstance(v, str) else v

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    def is_development(self) -> bool:
        return self.app_env == AppEnv.DEVELOPMENT

    def missing_module2_vars(self) -> list[str]:
        """Return names of required WhatsApp env vars that are not set."""
        required = {
            "WHATSAPP_ACCESS_TOKEN": self.whatsapp_access_token,
            "WHATSAPP_PHONE_NUMBER_ID": self.whatsapp_phone_number_id,
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN": self.whatsapp_webhook_verify_token,
        }
        return [name for name, val in required.items() if not val]

    def missing_module3_vars(self) -> list[str]:
        """Return names of required Google Sheets env vars that are not set."""
        required = {
            "GOOGLE_SERVICE_ACCOUNT_JSON_PATH": self.google_service_account_json_path,
            "INVENTORY_SPREADSHEET_ID": self.inventory_spreadsheet_id,
            "FAQ_SPREADSHEET_ID": self.faq_spreadsheet_id,
            "ORDERS_SPREADSHEET_ID": self.orders_spreadsheet_id,
        }
        return [name for name, val in required.items() if not val]

    def missing_module4_vars(self) -> list[str]:
        """Return names of required LLM env vars that are not set."""
        required = {
            "LLM_PROVIDER": self.llm_provider,
            "LLM_API_KEY": self.llm_api_key,
            "LLM_MODEL": self.llm_model,
        }
        return [name for name, val in required.items() if not val]


# ── Module-level singleton ─────────────────────────────────────────────────────
# Import `settings` wherever you need configuration.
# It is loaded once at startup and re-used everywhere.
settings = Settings()
