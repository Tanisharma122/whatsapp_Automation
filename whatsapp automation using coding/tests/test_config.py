"""
test_config.py — Tests for typed configuration loading and validation.

These tests verify that:
  - Settings can be loaded without any .env file (all optional fields default to None).
  - The helpers that list missing variables work correctly.
  - Secret values are never returned by the missing-variable helpers
    (they only return names).
"""
from app.config import Settings


def test_settings_load_with_defaults() -> None:
    """Settings should load successfully even with no .env file present."""
    s = Settings()
    assert s.app_name is not None
    assert s.app_version is not None


def test_settings_default_env_is_development() -> None:
    """Default environment should be 'development'."""
    s = Settings()
    assert s.app_env.value == "development"


def test_settings_default_log_level_is_info() -> None:
    """Default log level should be INFO."""
    s = Settings()
    assert s.log_level.value == "INFO"


def test_missing_module2_vars_returns_list() -> None:
    """missing_module2_vars() should return a list of strings."""
    s = Settings()
    result = s.missing_module2_vars()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, str)


def test_missing_module3_vars_returns_list() -> None:
    """missing_module3_vars() should return a list of strings."""
    s = Settings()
    result = s.missing_module3_vars()
    assert isinstance(result, list)


def test_missing_module4_vars_returns_list() -> None:
    """missing_module4_vars() should return a list of strings."""
    s = Settings()
    result = s.missing_module4_vars()
    assert isinstance(result, list)


def test_missing_vars_names_are_uppercase() -> None:
    """
    All names returned by missing_*_vars helpers must be uppercase
    environment variable names, not actual secret values.
    """
    s = Settings()
    all_missing = (
        s.missing_module2_vars()
        + s.missing_module3_vars()
        + s.missing_module4_vars()
    )
    for name in all_missing:
        assert name == name.upper(), f"Expected uppercase env var name, got: {name!r}"
        # Env var names contain only letters, digits, and underscores
        assert all(c.isalnum() or c == "_" for c in name), (
            f"Unexpected characters in var name: {name!r}"
        )


def test_no_optional_fields_present_when_env_is_empty() -> None:
    """
    When credentials are not set, optional fields should be None —
    not empty strings or fabricated defaults.
    """
    s = Settings(
        whatsapp_access_token=None,
        llm_api_key=None,
        google_service_account_json_path=None,
    )
    assert s.whatsapp_access_token is None
    assert s.llm_api_key is None
    assert s.google_service_account_json_path is None


def test_is_development_returns_bool() -> None:
    """is_development() should return a plain boolean."""
    s = Settings()
    result = s.is_development()
    assert isinstance(result, bool)


def test_all_three_modules_unconfigured_by_default() -> None:
    """
    When all credential fields are explicitly set to None, all three module
    groups should report missing variables — regardless of any .env file on disk.
    """
    s = Settings(
        # Explicitly clear all credentials so this test is isolated
        # from whatever is in the real .env file
        whatsapp_access_token=None,
        whatsapp_phone_number_id=None,
        whatsapp_webhook_verify_token=None,
        google_service_account_json_path=None,
        inventory_spreadsheet_id=None,
        faq_spreadsheet_id=None,
        orders_spreadsheet_id=None,
        llm_provider=None,
        llm_api_key=None,
        llm_model=None,
    )
    assert len(s.missing_module2_vars()) > 0, "Expected WhatsApp vars to be missing"
    assert len(s.missing_module3_vars()) > 0, "Expected Sheets vars to be missing"
    assert len(s.missing_module4_vars()) > 0, "Expected LLM vars to be missing"
