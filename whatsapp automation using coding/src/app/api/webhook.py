"""
webhook.py — WhatsApp webhook endpoints.

This router handles two things:

1. GET /webhook — Verification handshake
   When you register your webhook URL on the Meta developer portal, Meta sends
   a GET request with a challenge string. You must echo the challenge back
   within a few seconds to prove you own the server.

2. POST /webhook — Incoming messages
   Meta sends a POST request every time a customer sends your business a message.
   We must return HTTP 200 immediately, then process the message in the background.

Reference:
  https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.config import settings
from app.models.whatsapp import WhatsAppWebhookPayload
from app.services.message_processor import process_incoming_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


# ── GET /webhook — Meta verification handshake ─────────────────────────────────

@router.get(
    "",
    summary="WhatsApp webhook verification",
    description=(
        "Meta calls this endpoint once when you register your webhook URL. "
        "It sends a challenge string that we must echo back to confirm ownership."
    ),
)
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> Response:
    """
    Respond to Meta's webhook verification challenge.

    Meta sends:
      ?hub.mode=subscribe
      &hub.verify_token=<the token you configured>
      &hub.challenge=<random string to echo back>

    We return the challenge as plain text with 200 if the token matches,
    or 403 if it does not.
    """
    logger.info("Webhook verification request received (mode=%s)", hub_mode)

    verify_token = settings.whatsapp_webhook_verify_token

    if not verify_token:
        logger.error(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN is not configured — "
            "cannot verify webhook. Set this env var first."
        )
        raise HTTPException(status_code=500, detail="Webhook verify token not configured.")

    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("Webhook verification successful.")
        # ngrok-skip-browser-warning header bypasses ngrok's free-tier interstitial page
        # so Meta's verification request reaches our server directly.
        return Response(
            content=hub_challenge,
            media_type="text/plain",
            headers={"ngrok-skip-browser-warning": "1"},
        )

    logger.warning(
        "Webhook verification FAILED. "
        "hub.mode=%s token_match=%s",
        hub_mode,
        hub_verify_token == verify_token,  # logs True/False, not the token
    )
    raise HTTPException(status_code=403, detail="Verification failed.")


# ── POST /webhook — Incoming messages ─────────────────────────────────────────

@router.post(
    "",
    summary="Receive incoming WhatsApp messages",
    description=(
        "Meta POSTs here for every incoming message event. "
        "We return 200 immediately and process messages in the background."
    ),
)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Handle incoming WhatsApp webhook events.

    We ALWAYS return {"status": "received"} with HTTP 200 as fast as possible.
    If we return a non-200, Meta will retry, causing duplicate processing.

    The actual message handling happens in a BackgroundTask.
    """
    # Parse the raw body
    try:
        body = await request.json()
    except Exception:
        logger.warning("Received non-JSON webhook payload — ignoring.")
        # Still return 200 so Meta doesn't retry with the same bad payload
        return {"status": "received"}

    # Validate payload structure with Pydantic
    try:
        payload = WhatsAppWebhookPayload.model_validate(body)
    except ValidationError as exc:
        logger.warning("Webhook payload validation failed: %s — errors: %s — raw body: %s", exc.error_count(), exc.errors(), body)
        # Still 200 — malformed payloads won't improve with retries
        return {"status": "received"}

    # Confirm it's a WhatsApp event (not some other Meta product webhook)
    if payload.object != "whatsapp_business_account":
        logger.info("Ignoring non-WhatsApp webhook object: %s", payload.object)
        return {"status": "received"}

    # Extract and queue all messages in the payload for background processing
    messages_queued = 0
    for entry in payload.entry:
        for change in entry.changes:
            if change.field != "messages":
                continue
            value = change.value
            messages = value.messages or []
            contacts = value.contacts or []

            # Build a quick lookup for customer names
            name_lookup: dict[str, str] = {
                c.wa_id: c.profile.name for c in contacts
            }

            for message in messages:
                customer_name = name_lookup.get(message.from_, "Customer")
                background_tasks.add_task(
                    process_incoming_message,
                    message=message,
                    customer_name=customer_name,
                )
                messages_queued += 1

    if messages_queued:
        logger.info("Queued %d message(s) for background processing.", messages_queued)
    else:
        logger.debug("Webhook received but contained no new messages (may be a status update).")

    # IMPORTANT: Always return 200 quickly so Meta doesn't retry
    return {"status": "received"}
