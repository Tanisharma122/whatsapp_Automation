"""
whatsapp.py — Pydantic models for the WhatsApp Cloud API webhook payload.

These models represent the JSON structure that Meta sends to your webhook
when a customer sends you a WhatsApp message.

Reference:
  https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Granular payload models ────────────────────────────────────────────────────

class WhatsAppProfile(BaseModel):
    name: str


class WhatsAppContact(BaseModel):
    profile: WhatsAppProfile
    wa_id: str  # customer's WhatsApp phone number (without +)


class WhatsAppTextBody(BaseModel):
    body: str


class WhatsAppMessage(BaseModel):
    """
    A single message inside a webhook event.

    `type` tells us what kind of message this is.
    We currently handle "text"; others are logged and ignored safely.
    """
    id: str                             # unique message ID — used for idempotency
    from_: str = Field(alias="from")    # sender's phone number
    timestamp: str                      # Unix epoch string
    type: str                           # "text" | "image" | "audio" | "document" | ...
    text: Optional[WhatsAppTextBody] = None

    model_config = {"populate_by_name": True}

    def is_text(self) -> bool:
        return self.type == "text" and self.text is not None

    def get_text_body(self) -> Optional[str]:
        return self.text.body if self.text else None


class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: dict[str, Any]
    contacts: Optional[list[WhatsAppContact]] = None
    messages: Optional[list[WhatsAppMessage]] = None
    statuses: Optional[list[dict[str, Any]]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: list[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    """
    The top-level object Meta sends to your webhook endpoint.

    One payload can contain multiple entries and multiple messages per entry.
    We must handle all of them.
    """
    object: str   # should always be "whatsapp_business_account"
    entry: list[WhatsAppEntry]


# ── Outbound message models ────────────────────────────────────────────────────

class OutboundTextMessage(BaseModel):
    """Body sent to the WhatsApp Cloud API to send a text reply."""
    messaging_product: Literal["whatsapp"] = "whatsapp"
    recipient_type: Literal["individual"] = "individual"
    to: str                   # recipient phone number in E.164 format (e.g. "919876543210")
    type: Literal["text"] = "text"
    text: dict[str, str]      # {"body": "Your reply here"}

    @classmethod
    def create(cls, to: str, body: str) -> "OutboundTextMessage":
        return cls(to=to, text={"body": body})
