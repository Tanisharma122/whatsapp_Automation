"""
message_processor.py — Parses and routes incoming WhatsApp messages.

WHY THIS IS SEPARATE FROM THE WEBHOOK ENDPOINT:
  The webhook router's job is to validate the request and return HTTP 200
  to Meta as fast as possible (within 5 seconds).

  The actual work — understanding the message, calling the AI, writing to
  Google Sheets — takes longer and happens HERE, in a background task.

  This separation keeps the webhook responsive while allowing processing
  to take as long as needed.

CURRENT STATE (Module 5 — Full Integration):
  Incoming messages are routed to the AI service, which:
    1. Maintains conversation history per customer.
    2. Calls Google Gemini with the real menu and FAQ data.
    3. Detects ordering intent and validates orders against inventory.
    4. Writes confirmed orders to Google Sheets.
    5. Returns the reply to send back to the customer.
"""
from __future__ import annotations

import logging

from app.integrations.whatsapp_client import WhatsAppClient, WhatsAppClientError
from app.models.whatsapp import WhatsAppMessage
from app.services.ai_service import ai_service
from app.utils.idempotency import tracker

logger = logging.getLogger(__name__)

# Supported message types we know how to handle
_SUPPORTED_TYPES = {"text"}


async def process_incoming_message(message: WhatsAppMessage, customer_name: str) -> None:
    """
    Process a single incoming WhatsApp message.

    This runs as a FastAPI background task — the HTTP response is already
    sent to Meta before this function starts.

    Args:
        message:       The parsed WhatsApp message object.
        customer_name: Display name from the contact info in the webhook payload.
    """
    # Idempotency check — skip if we've already handled this message
    if tracker.is_duplicate(message.id):
        logger.info("Skipping duplicate message id=%s", message.id)
        return

    # Mask the sender phone number in logs (first 4 digits only)
    raw_from = message.from_
    masked_from = raw_from[:4] + "****" if len(raw_from) > 4 else "****"

    logger.info(
        "Processing message id=%s from=%s type=%s",
        message.id, masked_from, message.type,
    )

    # Handle unsupported message types gracefully
    if message.type not in _SUPPORTED_TYPES:
        logger.info(
            "Unsupported message type '%s' from %s — sending polite notice.",
            message.type, masked_from,
        )
        await _send_unsupported_type_notice(to=message.from_)
        return

    # --- Text message handling ------------------------------------------------
    text_body = message.get_text_body()
    if not text_body:
        logger.warning("Text message id=%s had no body — ignoring.", message.id)
        return

    logger.info("Received text from %s (length=%d chars)", masked_from, len(text_body))

    # ── AI SERVICE (Module 4 — live) ──────────────────────────────────────────
    try:
        reply = await ai_service.generate_reply(
            customer_phone=message.from_,
            customer_name=customer_name,
            text=text_body,
        )
    except Exception as exc:
        logger.exception("AI service error processing message id=%s: %s", message.id, exc)
        reply = (
            "Sorry, I'm having a technical issue right now. "
            "Please try again in a few minutes. 🙏"
        )
    # ─────────────────────────────────────────────────────────────────────────

    await _send_reply(to=message.from_, body=reply)


async def _send_reply(to: str, body: str) -> None:
    """Send a reply message, logging errors without crashing."""
    try:
        async with WhatsAppClient() as client:
            await client.send_text(to=to, body=body)
    except WhatsAppClientError as exc:
        # Log the error but don't crash — the customer will just not get a reply.
        logger.error("Failed to send reply: %s (status=%s)", exc, exc.status_code)
    except Exception as exc:
        logger.exception("Unexpected error sending reply: %s", exc)


async def _send_unsupported_type_notice(to: str) -> None:
    """Notify customer that their message type isn't supported yet."""
    await _send_reply(
        to=to,
        body="Sorry, I can only read text messages right now. Please type your question. 😊",
    )
