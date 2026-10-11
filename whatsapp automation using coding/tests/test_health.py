"""
test_health.py — Tests for the /health endpoint.

These tests require NO external services — no WhatsApp, Google Sheets,
or LLM keys needed. They run entirely offline.
"""
from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    """The /health endpoint must always return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_status_is_ok(client: TestClient) -> None:
    """The `status` field in the response must be 'ok'."""
    data = client.get("/health").json()
    assert data["status"] == "ok"


def test_health_contains_app_name(client: TestClient) -> None:
    """The response must include the application name."""
    data = client.get("/health").json()
    assert "app_name" in data
    assert len(data["app_name"]) > 0


def test_health_contains_version(client: TestClient) -> None:
    """The response must include a version string."""
    data = client.get("/health").json()
    assert "version" in data


def test_health_contains_timestamp(client: TestClient) -> None:
    """The response must include an ISO-format timestamp."""
    data = client.get("/health").json()
    assert "timestamp" in data
    # Ensure it looks like an ISO datetime (contains T separator)
    assert "T" in data["timestamp"]


def test_health_modules_present(client: TestClient) -> None:
    """The `modules` block must include whatsapp, google_sheets, and llm."""
    data = client.get("/health").json()
    assert "modules" in data
    modules = data["modules"]
    assert "whatsapp" in modules
    assert "google_sheets" in modules
    assert "llm" in modules


def test_health_module_structure(client: TestClient) -> None:
    """Each module entry must have `configured` (bool) and `missing_vars` (list)."""
    modules = client.get("/health").json()["modules"]
    for name, status in modules.items():
        assert "configured" in status, f"Module {name} missing 'configured' key"
        assert "missing_vars" in status, f"Module {name} missing 'missing_vars' key"
        assert isinstance(status["configured"], bool)
        assert isinstance(status["missing_vars"], list)


def test_health_unconfigured_modules_report_missing_var_names(client: TestClient) -> None:
    """
    When a module is not configured, missing_vars must list variable NAMES,
    not values. We check that none of the listed names contain secret-looking
    content (they should be uppercase env-var names, not long tokens).
    """
    modules = client.get("/health").json()["modules"]
    for name, status in modules.items():
        for var_name in status["missing_vars"]:
            # Variable names are short, uppercase, underscored strings
            assert var_name == var_name.upper(), (
                f"Expected uppercase var name, got: {var_name!r}"
            )
            # They should not contain long strings that look like tokens (>50 chars)
            assert len(var_name) < 60, (
                f"Suspiciously long var name — could be leaking a value: {var_name!r}"
            )
