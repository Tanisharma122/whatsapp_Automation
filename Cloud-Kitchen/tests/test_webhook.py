"""
test_webhook.py — Tests for the WhatsApp webhook endpoints.

All tests are offline — no real Meta API calls, no credentials needed.

We test:
  1. GET /webhook verification handshake (success + failure cases)
  2. POST /webhook — well-formed payloads
  3. POST /webhook — malformed payloads (must still return 200)
  4. POST /webhook — status-update payloads (no messages, still 200)
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_TOKEN = "test_verify_token_123"

# A minimal but real-shaped WhatsApp webhook payload with one text message
SAMPLE_TEXT_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "1234567890",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "1234567890",
                            "phone_number_id": "987654321",
                        },
                        "contacts": [
                            {"profile": {"name": "Test Customer"}, "wa_id": "919876543210"}
                        ],
                        "messages": [
                            {
                                "id": "wamid.unique_message_id_001",
                                "from": "919876543210",
                                "timestamp": "1700000000",
                                "type": "text",
                                "text": {"body": "Hi, what's on the menu?"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

# A payload with an unsupported message type (image)
SAMPLE_IMAGE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "1234567890",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {},
                        "contacts": [
                            {"profile": {"name": "Test Customer"}, "wa_id": "919876543210"}
                        ],
                        "messages": [
                            {
                                "id": "wamid.unique_message_id_002",
                                "from": "919876543210",
                                "timestamp": "1700000001",
                                "type": "image",
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

# A status-update payload (delivery receipt) — no "messages" key
SAMPLE_STATUS_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "1234567890",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {},
                        "statuses": [
                            {
                                "id": "wamid.some_message_id",
                                "status": "delivered",
                                "timestamp": "1700000002",
                                "recipient_id": "919876543210",
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


# ── GET /webhook — Verification ────────────────────────────────────────────────

def test_webhook_verification_success(client: TestClient) -> None:
    """Valid token + subscribe mode should return the challenge string with 200."""
    with patch("app.api.webhook.settings") as mock_settings:
        mock_settings.whatsapp_webhook_verify_token = VALID_TOKEN
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VALID_TOKEN,
                "hub.challenge": "challenge_xyz_789",
            },
        )
    assert response.status_code == 200
    assert response.text == "challenge_xyz_789"


def test_webhook_verification_wrong_token(client: TestClient) -> None:
    """Wrong token should return 403."""
    with patch("app.api.webhook.settings") as mock_settings:
        mock_settings.whatsapp_webhook_verify_token = VALID_TOKEN
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_xyz_789",
            },
        )
    assert response.status_code == 403


def test_webhook_verification_wrong_mode(client: TestClient) -> None:
    """Wrong hub.mode should return 403."""
    with patch("app.api.webhook.settings") as mock_settings:
        mock_settings.whatsapp_webhook_verify_token = VALID_TOKEN
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "unsubscribe",
                "hub.verify_token": VALID_TOKEN,
                "hub.challenge": "challenge_xyz_789",
            },
        )
    assert response.status_code == 403


def test_webhook_verification_missing_token_config(client: TestClient) -> None:
    """If WHATSAPP_WEBHOOK_VERIFY_TOKEN is not configured, return 500."""
    with patch("app.api.webhook.settings") as mock_settings:
        mock_settings.whatsapp_webhook_verify_token = None
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VALID_TOKEN,
                "hub.challenge": "challenge_xyz_789",
            },
        )
    assert response.status_code == 500


# ── POST /webhook — Incoming messages ─────────────────────────────────────────

def test_webhook_post_text_message_returns_200(client: TestClient) -> None:
    """A valid text message payload must always return 200."""
    with patch("app.services.message_processor.WhatsAppClient"):
        response = client.post("/webhook", json=SAMPLE_TEXT_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_webhook_post_image_message_returns_200(client: TestClient) -> None:
    """Unsupported message types must still return 200 (not crash)."""
    with patch("app.services.message_processor.WhatsAppClient"):
        response = client.post("/webhook", json=SAMPLE_IMAGE_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_webhook_post_status_update_returns_200(client: TestClient) -> None:
    """Delivery status payloads (no messages) must return 200."""
    response = client.post("/webhook", json=SAMPLE_STATUS_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_webhook_post_malformed_json_returns_200(client: TestClient) -> None:
    """
    Even if the payload is not valid JSON (e.g., a plain string),
    we must return 200 so Meta doesn't keep retrying.
    """
    response = client.post(
        "/webhook",
        content="this is not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200


def test_webhook_post_wrong_object_type_returns_200(client: TestClient) -> None:
    """Payloads for other Meta products (not WhatsApp) must return 200."""
    response = client.post(
        "/webhook",
        json={"object": "instagram", "entry": []},
    )
    assert response.status_code == 200


def test_webhook_post_empty_entry_list_returns_200(client: TestClient) -> None:
    """A payload with an empty entry list must not crash."""
    response = client.post(
        "/webhook",
        json={"object": "whatsapp_business_account", "entry": []},
    )
    assert response.status_code == 200
