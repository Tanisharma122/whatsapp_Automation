"""
whatsapp_client.py — WhatsApp Cloud API client for sending messages.

This module sends messages FROM your business number TO customers.

Reference:
  https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages

Authentication:
  Every request must include your WhatsApp Access Token in the Authorization
  header. This token is read from the environment — never hardcoded.

Error handling:
  - 401 Unauthorized  → bad or expired access token
  - 429 Too Many Reqs → rate limit hit; we log and raise
  - 4xx              → bad request (invalid recipient, bad payload)
  - 5xx              → Meta server error; safe to retry
  - Network errors   → logged and re-raised as WhatsAppClientError
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings
from app.models.whatsapp import OutboundTextMessage

logger = logging.getLogger(__name__)

# Official WhatsApp Cloud API base URL
_BASE_URL = "https://graph.facebook.com/v21.0"


class WhatsAppClientError(Exception):
    """Raised when the WhatsApp API returns an error or the network fails."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WhatsAppClient:
    """
    Thin async client for the WhatsApp Cloud API.

    Usage:
        async with WhatsAppClient() as client:
            await client.send_text(to="919876543210", body="Hello!")
    """

    def __init__(self) -> None:
        self._token: Optional[str] = settings.whatsapp_access_token
        self._phone_number_id: Optional[str] = settings.whatsapp_phone_number_id
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "WhatsAppClient":
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=httpx.Timeout(10.0),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()

    def _require_config(self) -> tuple[str, str]:
        """
        Validate that the required config is present before making any API call.
        Raises WhatsAppClientError with the variable NAME (not value) if missing.
        """
        missing = settings.missing_module2_vars()
        if missing:
            raise WhatsAppClientError(
                f"WhatsApp client not configured. Missing env vars: {missing}"
            )
        # At this point we know they're non-None
        return self._token, self._phone_number_id  # type: ignore[return-value]

    async def send_text(self, to: str, body: str) -> dict:
        """
        Send a plain-text WhatsApp message.

        Args:
            to:   Recipient phone number in E.164 format WITHOUT the '+'.
                  Example: "919876543210" for +91 98765 43210
            body: The text to send. Keep under 4096 characters.

        Returns:
            The parsed JSON response from the WhatsApp API.

        Raises:
            WhatsAppClientError: On any API or network error.
        """
        if not self._client:
            raise RuntimeError("Use 'async with WhatsAppClient() as client:' pattern.")

        token, phone_number_id = self._require_config()

        payload = OutboundTextMessage.create(to=to, body=body)

        # We log the recipient's number masked, never in full
        masked_to = to[:4] + "****" + to[-2:] if len(to) > 6 else "****"
        logger.info("Sending text message to %s", masked_to)

        try:
            response = await self._client.post(
                f"/{phone_number_id}/messages",
                json=payload.model_dump(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.TimeoutException as exc:
            raise WhatsAppClientError("Request to WhatsApp API timed out.") from exc
        except httpx.NetworkError as exc:
            raise WhatsAppClientError(f"Network error contacting WhatsApp API: {exc}") from exc

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict:
        """Parse the API response and raise on errors."""
        if response.status_code == 200:
            logger.info("Message sent successfully (status=200)")
            return response.json()

        if response.status_code == 401:
            raise WhatsAppClientError(
                "WhatsApp API authentication failed. Check WHATSAPP_ACCESS_TOKEN.",
                status_code=401,
            )

        if response.status_code == 429:
            raise WhatsAppClientError(
                "WhatsApp API rate limit exceeded. Try again later.",
                status_code=429,
            )

        # Log the status code but NOT the response body (may contain sensitive info)
        logger.error(
            "WhatsApp API error: status=%s", response.status_code
        )
        raise WhatsAppClientError(
            f"WhatsApp API returned status {response.status_code}.",
            status_code=response.status_code,
        )
