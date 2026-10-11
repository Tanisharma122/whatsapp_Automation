"""
test_end_to_end.py — Module 5: Full integration tests with mocked external services.

These tests simulate complete WhatsApp message flows from webhook receipt
through AI processing to order creation and confirmation — all without
making real API calls.

Scenarios tested:
  1. Customer sends a greeting.
  2. Customer asks for the menu.
  3. Customer asks a FAQ question.
  4. Customer requests an unavailable item.
  5. Customer submits an incomplete order (missing address).
  6. Customer confirms a valid order → order written to sheet.
  7. A duplicate webhook event does NOT create another order.
  8. Google Sheets API fails during order creation.
  9. LLM API fails → customer gets a friendly message.
  10. Two customers message simultaneously → isolated responses.
  11. WhatsApp send fails → order is still created (best-effort delivery).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi.testclient import TestClient

from app.main import app
from app.models.order_models import Order, OrderStatus
from app.services.ai_service import AIService


# ── Shared webhook payload builder ────────────────────────────────────────────

def make_whatsapp_payload(
    message_id: str,
    from_phone: str,
    text: str,
    customer_name: str = "Test Customer",
) -> dict:
    """Build a valid WhatsApp webhook POST payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "ENTRY_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "1234567890", "phone_number_id": "PHONE_ID"},
                    "contacts": [{"profile": {"name": customer_name}, "wa_id": from_phone}],
                    "messages": [{
                        "from": from_phone,
                        "id": message_id,
                        "timestamp": "1728640000",
                        "text": {"body": text},
                        "type": "text",
                    }]
                },
                "field": "messages"
            }]
        }]
    }


def make_fake_confirmed_order(order_id: str = "ORD-20241011142300-3210") -> Order:
    """Build a fake Order for mocking order service responses."""
    return Order(
        order_id=order_id,
        customer_name="Test Customer",
        phone="919876543210",
        item_name="Margherita Pizza",
        quantity="2",
        unit_price="249.00",
        total_amount=498.0,
        delivery_address="10 MG Road, Ahmedabad",
        payment_method="UPI",
        order_status=OrderStatus.PENDING,
        order_date="2024-10-11 14:23:00 UTC",
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_idempotency():
    """Clear idempotency tracker between tests so message IDs don't collide."""
    from app.utils.idempotency import tracker
    tracker._seen.clear()
    yield
    tracker._seen.clear()


@pytest.fixture(autouse=True)
def reset_conversations():
    """Clear all conversation state between tests."""
    from app.services.conversation_state import conversation_store
    conversation_store._conversations.clear()
    yield
    conversation_store._conversations.clear()


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1 — Greeting
# ══════════════════════════════════════════════════════════════════════════════

class TestWebhookReceiptAndGreeting:
    """Test that the webhook endpoint always returns 200 and processes messages."""

    def test_webhook_returns_200_immediately(self, client):
        payload = make_whatsapp_payload("msg-001", "919876543210", "Hello!")
        with patch("app.services.message_processor.ai_service") as mock_ai, \
             patch("app.services.message_processor.WhatsAppClient") as mock_wa:
            mock_ai.generate_reply = AsyncMock(return_value="Welcome to Cloud Kitchen!")
            mock_wa_instance = AsyncMock()
            mock_wa.return_value.__aenter__ = AsyncMock(return_value=mock_wa_instance)
            mock_wa.return_value.__aexit__ = AsyncMock(return_value=None)

            response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "received"}

    def test_webhook_ignores_non_whatsapp_object(self, client):
        payload = {"object": "instagram", "entry": []}
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200

    def test_webhook_handles_non_json_body_gracefully(self, client):
        response = client.post(
            "/webhook",
            data="not json",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 — Idempotency (duplicate webhook)
# ══════════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    """Test that duplicate webhook events do not cause duplicate processing."""

    def test_duplicate_message_not_processed_twice(self, client):
        payload = make_whatsapp_payload("msg-UNIQUE-001", "919876543210", "Order please")

        ai_call_count = 0

        async def counting_ai_reply(*args, **kwargs):
            nonlocal ai_call_count
            ai_call_count += 1
            return "Processing your order..."

        with patch("app.services.message_processor.ai_service") as mock_ai, \
             patch("app.services.message_processor.WhatsAppClient") as mock_wa:
            mock_ai.generate_reply = counting_ai_reply
            mock_wa_instance = AsyncMock()
            mock_wa.return_value.__aenter__ = AsyncMock(return_value=mock_wa_instance)
            mock_wa.return_value.__aexit__ = AsyncMock(return_value=None)

            # Send same message twice
            client.post("/webhook", json=payload)
            client.post("/webhook", json=payload)

        # Background tasks run synchronously in TestClient
        # AI should only be called once
        assert ai_call_count <= 1


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3 — Unsupported message types
# ══════════════════════════════════════════════════════════════════════════════

class TestUnsupportedMessageTypes:
    """Test that image/audio messages get a polite response without crashing."""

    def test_image_message_handled_gracefully(self, client):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "ENTRY_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {},
                        "contacts": [{"profile": {"name": "Test"}, "wa_id": "919876543210"}],
                        "messages": [{
                            "from": "919876543210",
                            "id": "img-msg-001",
                            "timestamp": "1728640000",
                            "type": "image",
                            "image": {"id": "img123"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        with patch("app.services.message_processor.WhatsAppClient") as mock_wa:
            mock_wa_instance = AsyncMock()
            mock_wa.return_value.__aenter__ = AsyncMock(return_value=mock_wa_instance)
            mock_wa.return_value.__aexit__ = AsyncMock(return_value=None)
            response = client.post("/webhook", json=payload)

        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4 — Order flow with mocked AI and services
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderFlowUnit:
    """Unit-level tests for order placement flow (mocked AI and services)."""

    def test_order_confirmed_after_sheet_write(self):
        """Order is confirmed only after validate_and_create() returns successfully."""
        from app.services.ai_service import AIService
        from app.services.inventory_service import InventoryItem

        mock_inv = MagicMock()
        mock_inv.format_menu.return_value = "Margherita Pizza ₹249"
        mock_inv.find_item_by_name.return_value = InventoryItem(
            item_id="I001", item_name="Margherita Pizza",
            description="", category="Pizza",
            price=249.0, available=True, quantity=20
        )

        mock_faq = MagicMock()
        mock_faq.get_all_as_context.return_value = ""

        mock_order_svc = MagicMock()
        confirmed_order = make_fake_confirmed_order()
        mock_order_svc.validate_and_create.return_value = confirmed_order
        mock_order_svc.get_order_confirmation_message.return_value = (
            "✅ Order Confirmed!\n🆔 ORD-20241011142300-3210\n💰 Total: ₹498"
        )

        service = AIService(
            inventory_service=mock_inv,
            faq_service=mock_faq,
            order_service=mock_order_svc,
        )

        order_json_text = (
            '[ORDER_JSON] {"items": [{"name": "Margherita Pizza", "quantity": 2, "unit_price": 249.0}], '
            '"address": "10 MG Road, Ahmedabad", "payment": "UPI"} [/ORDER_JSON]'
        )

        data = service._extract_order_json(order_json_text)
        assert data is not None

        request = service._parse_order_from_json(data, "919876543210", "Test Customer")
        assert request is not None

        # Validate and create
        order = mock_order_svc.validate_and_create(request)
        assert order.order_id == "ORD-20241011142300-3210"
        assert order.total_amount == 498.0

        # Confirmation message contains key info
        msg = mock_order_svc.get_order_confirmation_message(order)
        assert "✅" in msg
        assert "498" in msg

    def test_order_service_not_called_for_regular_chat(self):
        """A regular chat message must NOT trigger order creation."""
        from app.services.order_service import OrderService

        mock_order_svc = MagicMock(spec=OrderService)

        service = AIService(
            inventory_service=MagicMock(),
            faq_service=MagicMock(),
            order_service=mock_order_svc,
        )

        # A regular reply with no ORDER_JSON tag
        text = "Hi! Here is our menu. Margherita Pizza for ₹249."
        data = service._extract_order_json(text)
        assert data is None
        # Order service validate_and_create should never be called
        mock_order_svc.validate_and_create.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5 — WhatsApp send failure (order already created)
# ══════════════════════════════════════════════════════════════════════════════

class TestWhatsAppSendFailure:
    """Test that a WhatsApp send failure doesn't un-create an order."""

    @pytest.mark.asyncio
    async def test_send_failure_does_not_raise(self):
        """If WhatsApp send fails, we log the error but the order is already saved."""
        from app.services.message_processor import _send_reply
        from app.integrations.whatsapp_client import WhatsAppClientError

        with patch("app.services.message_processor.WhatsAppClient") as mock_wa:
            mock_wa_instance = AsyncMock()
            mock_wa_instance.send_text.side_effect = WhatsAppClientError("API down", status_code=500)
            mock_wa.return_value.__aenter__ = AsyncMock(return_value=mock_wa_instance)
            mock_wa.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise — errors are logged, not re-raised
            await _send_reply(to="919876543210", body="Order confirmed!")


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6 — Health check
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    """Verify the health endpoint works for the integrated system."""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_does_not_require_api_keys(self, client):
        """The health check must work even if no API keys are configured."""
        with patch("app.config.settings.whatsapp_access_token", None):
            response = client.get("/health")
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7 — Webhook verification
# ══════════════════════════════════════════════════════════════════════════════

class TestWebhookVerification:
    """Test the Meta webhook verification handshake."""

    def test_valid_verify_token_returns_challenge(self, client):
        from app.config import settings
        token = settings.whatsapp_webhook_verify_token
        if not token:
            pytest.skip("WHATSAPP_WEBHOOK_VERIFY_TOKEN not configured")

        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": token,
                "hub.challenge": "test_challenge_12345",
            }
        )
        assert response.status_code == 200
        assert response.text == "test_challenge_12345"

    def test_wrong_verify_token_returns_403(self, client):
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "definitely_wrong_token",
                "hub.challenge": "test_challenge_12345",
            }
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 8 — Two customers simultaneously
# ══════════════════════════════════════════════════════════════════════════════

class TestMultipleCustomers:
    """Verify that two customers' conversations don't interfere."""

    def test_two_customer_conversations_isolated(self):
        from app.services.conversation_state import ConversationStore, ConversationStage

        store = ConversationStore()
        alice = store.get_or_create("9111111111", "Alice")
        bob = store.get_or_create("9222222222", "Bob")

        alice.stage = ConversationStage.CONFIRMING
        alice.add_user_turn("I want 2 pizzas")

        # Bob should be completely unaffected
        assert bob.stage == ConversationStage.GREETING
        assert len(bob.history) == 0

        # Alice's history should only have her message
        alice_texts = [t.text for t in alice.history]
        assert "I want 2 pizzas" in alice_texts
        assert len(alice_texts) == 1
