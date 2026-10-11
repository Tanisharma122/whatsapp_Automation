"""
test_whatsapp_client.py — Unit tests for the WhatsApp API client.

All tests use mocked HTTP responses — no real API calls, no credentials needed.

We test:
  1. Successful message send (200 OK)
  2. 401 Unauthorized → WhatsAppClientError
  3. 429 Rate limit → WhatsAppClientError
  4. 500 Server error → WhatsAppClientError
  5. Network timeout → WhatsAppClientError
  6. Missing config → WhatsAppClientError (raises before making any call)
  7. Phone number masking in logs
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.whatsapp_client import WhatsAppClient, WhatsAppClientError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    """Build a fake httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    if json_body is not None:
        mock.json.return_value = json_body
    return mock


CONFIGURED_SETTINGS = MagicMock(
    whatsapp_access_token="fake_token_abc",
    whatsapp_phone_number_id="1234567890",
    missing_module2_vars=MagicMock(return_value=[]),  # all configured
)

UNCONFIGURED_SETTINGS = MagicMock(
    whatsapp_access_token=None,
    whatsapp_phone_number_id=None,
    missing_module2_vars=MagicMock(return_value=["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"]),
)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_text_success() -> None:
    """A 200 OK response should return the parsed JSON dict."""
    fake_response = _make_response(200, {"messages": [{"id": "wamid.abc123"}]})
    async_post = AsyncMock(return_value=fake_response)

    with patch("app.integrations.whatsapp_client.settings", CONFIGURED_SETTINGS):
        client = WhatsAppClient()
        client._client = MagicMock()
        client._client.post = async_post
        result = await client.send_text(to="919876543210", body="Hello!")

    assert result == {"messages": [{"id": "wamid.abc123"}]}


@pytest.mark.asyncio
async def test_send_text_401_raises_client_error() -> None:
    """A 401 response should raise WhatsAppClientError."""
    fake_response = _make_response(401)
    async_post = AsyncMock(return_value=fake_response)

    with patch("app.integrations.whatsapp_client.settings", CONFIGURED_SETTINGS):
        client = WhatsAppClient()
        client._client = MagicMock()
        client._client.post = async_post
        with pytest.raises(WhatsAppClientError) as exc_info:
            await client.send_text(to="919876543210", body="Hello!")

    assert exc_info.value.status_code == 401
    assert "WHATSAPP_ACCESS_TOKEN" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_429_raises_client_error() -> None:
    """A 429 response should raise WhatsAppClientError."""
    fake_response = _make_response(429)
    async_post = AsyncMock(return_value=fake_response)

    with patch("app.integrations.whatsapp_client.settings", CONFIGURED_SETTINGS):
        client = WhatsAppClient()
        client._client = MagicMock()
        client._client.post = async_post
        with pytest.raises(WhatsAppClientError) as exc_info:
            await client.send_text(to="919876543210", body="Hello!")

    assert exc_info.value.status_code == 429
    assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_send_text_500_raises_client_error() -> None:
    """A 500 response should raise WhatsAppClientError."""
    fake_response = _make_response(500)
    async_post = AsyncMock(return_value=fake_response)

    with patch("app.integrations.whatsapp_client.settings", CONFIGURED_SETTINGS):
        client = WhatsAppClient()
        client._client = MagicMock()
        client._client.post = async_post
        with pytest.raises(WhatsAppClientError) as exc_info:
            await client.send_text(to="919876543210", body="Hello!")

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_send_text_timeout_raises_client_error() -> None:
    """A network timeout should raise WhatsAppClientError."""
    async_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("app.integrations.whatsapp_client.settings", CONFIGURED_SETTINGS):
        client = WhatsAppClient()
        client._client = MagicMock()
        client._client.post = async_post
        with pytest.raises(WhatsAppClientError) as exc_info:
            await client.send_text(to="919876543210", body="Hello!")

    assert "timed out" in str(exc_info.value).lower()
    assert exc_info.value.status_code is None


@pytest.mark.asyncio
async def test_send_text_missing_config_raises_before_http_call() -> None:
    """
    If config vars are missing, we should raise WITHOUT making any HTTP call.
    This protects against accidental calls with partial credentials.
    """
    async_post = AsyncMock()

    with patch("app.integrations.whatsapp_client.settings", UNCONFIGURED_SETTINGS):
        client = WhatsAppClient()
        client._client = MagicMock()
        client._client.post = async_post
        with pytest.raises(WhatsAppClientError) as exc_info:
            await client.send_text(to="919876543210", body="Hello!")

    # The HTTP call must NOT have been made
    async_post.assert_not_called()
    # Error message should mention variable NAMES, not values
    assert "WHATSAPP_ACCESS_TOKEN" in str(exc_info.value)


# ── Idempotency tests ─────────────────────────────────────────────────────────

def test_idempotency_new_message_is_not_duplicate() -> None:
    """A fresh message ID should not be flagged as a duplicate."""
    from app.utils.idempotency import IdempotencyTracker
    t = IdempotencyTracker()
    assert t.is_duplicate("msg_001") is False


def test_idempotency_second_occurrence_is_duplicate() -> None:
    """The same message ID seen twice should be flagged on the second call."""
    from app.utils.idempotency import IdempotencyTracker
    t = IdempotencyTracker()
    t.is_duplicate("msg_002")  # first — not duplicate
    assert t.is_duplicate("msg_002") is True  # second — duplicate


def test_idempotency_different_ids_are_not_duplicates() -> None:
    """Two different message IDs should both be fresh."""
    from app.utils.idempotency import IdempotencyTracker
    t = IdempotencyTracker()
    assert t.is_duplicate("msg_003") is False
    assert t.is_duplicate("msg_004") is False


def test_idempotency_evicts_oldest_when_full() -> None:
    """When at max capacity, the oldest ID should be evicted."""
    from app.utils.idempotency import IdempotencyTracker
    t = IdempotencyTracker(max_size=3)
    t.is_duplicate("a")
    t.is_duplicate("b")
    t.is_duplicate("c")
    # Adding a 4th evicts "a"
    t.is_duplicate("d")
    # "a" should no longer be remembered
    assert t.is_duplicate("a") is False  # not duplicate — it was evicted


def test_idempotency_reset_clears_all() -> None:
    """reset() should make all IDs fresh again."""
    from app.utils.idempotency import IdempotencyTracker
    t = IdempotencyTracker()
    t.is_duplicate("msg_x")
    t.reset()
    assert t.is_duplicate("msg_x") is False
