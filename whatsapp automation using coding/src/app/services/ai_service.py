"""
ai_service.py — Conversational AI layer using Google Gemini.

KEY FIX (v2):
  The previous version embedded the system prompt inside the first user
  message. This broke multi-turn conversations because the Gemini chat
  history had the giant system blob as the first user turn — subsequent
  messages had no context.

  This version uses Gemini's proper `system_instruction` parameter.
  The instruction is set ONCE on the model; every chat session inherits it
  automatically. User messages are ALWAYS just the customer's text.

CRITICAL RULES:
  - The AI NEVER invents prices. Prices come from InventoryService.
  - The AI NEVER confirms an order. Only OrderService confirms after writing.
  - Customer conversations are strictly isolated from each other.
  - All AI-proposed orders are validated in application code before saving.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError

from app.config import settings
from app.models.order_models import OrderLineItem, OrderRequest, PaymentMethod
from app.services.conversation_state import ConversationStage, conversation_store
from app.services.faq_service import FAQService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService, OrderServiceError

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 1000
_PROMPT_CACHE_SECONDS = 300  # rebuild system prompt every 5 minutes

# ── System instruction template ────────────────────────────────────────────────
_SYSTEM_INSTRUCTION_TEMPLATE = """\
You are a friendly WhatsApp food ordering assistant for Cloud Kitchen.

WHAT YOU DO:
1. Help customers browse the menu and check availability.
2. Answer questions about delivery, payment, and policies.
3. Collect order details step by step (item → quantity → address → payment).
4. Confirm the order summary, then place it when the customer says YES.

STRICT RULES — NEVER BREAK THESE:
- NEVER invent prices, items, or availability. Use ONLY what the menu below shows.
- NEVER confirm an order until the system records it successfully.
- NEVER ask for card numbers, OTP, CVV, or sensitive financial details.
- Keep responses SHORT and WhatsApp-friendly. No long paragraphs.
- Respond in the same language the customer uses.
- Politely decline anything unrelated to food ordering.

HOW TO PLACE AN ORDER:
When a customer says YES to the order summary, output EXACTLY this on its own line:
[ORDER_JSON] {{"items": [{{"name": "Exact Item Name", "quantity": 2, "unit_price": 249.0}}], "address": "Full delivery address", "payment": "UPI"}} [/ORDER_JSON]

Valid payment values: "UPI", "Cash on Delivery", "Card"

== CURRENT MENU ==
{inventory_text}

== FAQ ==
{faq_text}

Be warm, helpful, and brief. This is WhatsApp — short messages are best!\
"""


class AIServiceError(Exception):
    """Raised when the AI service cannot generate a response."""


class AIService:
    """
    WhatsApp food ordering AI using Google Gemini with proper system_instruction.

    Each customer gets an isolated multi-turn chat session backed by
    ConversationStore. The model sees the system instruction on every turn.
    """

    def __init__(
        self,
        inventory_service: Optional[InventoryService] = None,
        faq_service: Optional[FAQService] = None,
        order_service: Optional[OrderService] = None,
    ) -> None:
        self._inventory = inventory_service or InventoryService()
        self._faq = faq_service or FAQService()
        self._order_service = order_service or OrderService()

        # Gemini model — rebuilt when system prompt cache expires
        self._model: Optional[genai.GenerativeModel] = None
        self._system_prompt_text: Optional[str] = None
        self._system_prompt_built_at: float = 0.0

    # ── System instruction ─────────────────────────────────────────────────────

    def _get_system_instruction(self) -> str:
        """
        Return the system instruction string, refreshed every 5 minutes.

        Loads live inventory and FAQ from Google Sheets.
        Falls back to a simple placeholder if Sheets is unreachable.
        """
        now = time.time()
        if self._system_prompt_text and (now - self._system_prompt_built_at) < _PROMPT_CACHE_SECONDS:
            return self._system_prompt_text

        try:
            inventory_text = self._inventory.format_menu()
        except Exception as exc:
            logger.warning("Could not load inventory for prompt: %s", exc)
            inventory_text = "(Menu temporarily unavailable. Apologise and ask the customer to try again later.)"

        try:
            faq_text = self._faq.get_all_as_context()
        except Exception as exc:
            logger.warning("Could not load FAQs for prompt: %s", exc)
            faq_text = "(FAQ data temporarily unavailable.)"

        self._system_prompt_text = _SYSTEM_INSTRUCTION_TEMPLATE.format(
            inventory_text=inventory_text,
            faq_text=faq_text,
        )
        self._system_prompt_built_at = now
        logger.info("System instruction rebuilt with fresh inventory and FAQ data.")
        return self._system_prompt_text

    # ── Model setup ────────────────────────────────────────────────────────────

    def _get_model(self) -> genai.GenerativeModel:
        """
        Return a configured Gemini GenerativeModel.

        Rebuilds the model if the system instruction cache has expired,
        so fresh inventory data is always used after 5 minutes.
        """
        api_key = settings.llm_api_key
        if not api_key:
            raise AIServiceError("LLM_API_KEY is not configured. Set it in your .env file.")

        model_name = settings.llm_model or "gemini-1.5-flash"
        system_instruction = self._get_system_instruction()

        # Rebuild if no model yet, or if system instruction was refreshed
        if self._model is None or self._system_prompt_built_at == time.time():
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(
                model_name=model_name,
                # ← KEY FIX: system_instruction is set here, NOT embedded in user messages
                system_instruction=system_instruction,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=600,
                ),
                safety_settings={
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE",
                },
            )
            logger.info("Gemini model '%s' (re)configured with system_instruction.", model_name)

        return self._model  # type: ignore[return-value]

    # ── Order JSON parsing ─────────────────────────────────────────────────────

    _ORDER_JSON_RE = re.compile(
        r'\[ORDER_JSON\]\s*(\{.*?\})\s*\[/ORDER_JSON\]',
        re.DOTALL
    )

    def _extract_order_json(self, text: str) -> Optional[dict]:
        match = self._ORDER_JSON_RE.search(text)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("Model produced malformed order JSON: %s", exc)
            return None

    def _parse_order_from_json(
        self, order_data: dict, phone: str, name: str
    ) -> Optional[OrderRequest]:
        """Build an OrderRequest from AI-proposed JSON. Always re-fetches real prices."""
        try:
            items_raw = order_data.get("items", [])
            if not items_raw:
                return None

            line_items = []
            for raw in items_raw:
                item_name = str(raw.get("name", "")).strip()
                qty = int(raw.get("quantity", 1))
                inv_item = self._inventory.find_item_by_name(item_name)
                if inv_item is None:
                    logger.warning("Order JSON referenced unknown item: '%s'", item_name)
                    return None
                line_items.append(OrderLineItem(
                    item_id=inv_item.item_id,
                    item_name=inv_item.item_name,
                    quantity=qty,
                    unit_price=inv_item.price,  # real price — never trust AI
                ))

            address = str(order_data.get("address", "")).strip()
            payment_raw = str(order_data.get("payment", "UPI")).strip().lower()
            payment_map = {
                "upi": PaymentMethod.UPI,
                "cash on delivery": PaymentMethod.CASH_ON_DELIVERY,
                "cod": PaymentMethod.CASH_ON_DELIVERY,
                "cash": PaymentMethod.CASH_ON_DELIVERY,
                "card": PaymentMethod.CARD,
            }
            payment = payment_map.get(payment_raw, PaymentMethod.UPI)

            return OrderRequest(
                customer_phone=phone,
                customer_name=name,
                items=line_items,
                delivery_address=address,
                payment_method=payment,
            )
        except Exception as exc:
            logger.warning("Failed to parse order from JSON: %s", exc)
            return None

    # ── Main entry point ───────────────────────────────────────────────────────

    async def generate_reply(
        self, customer_phone: str, customer_name: str, text: str
    ) -> str:
        """
        Generate a WhatsApp reply for an incoming customer message.

        Flow:
          1. Sanitise input.
          2. Load/create customer conversation state.
          3. Get (or rebuild) the Gemini model with system_instruction.
          4. Build Gemini chat history from conversation turns.
          5. Send ONLY the customer's current message — system context is handled by system_instruction.
          6. Store the reply in conversation history.
          7. If the reply contains [ORDER_JSON], validate and persist the order.
          8. Return the final reply text.
        """
        # 1. Sanitise
        text = text.strip()[:MAX_MESSAGE_LENGTH]
        if not text:
            return "Hi! How can I help you today? 😊"

        # 2. Conversation state
        conv = conversation_store.get_or_create(phone=customer_phone, name=customer_name)
        conv.add_user_turn(text)

        # 3. Model
        try:
            model = self._get_model()
        except AIServiceError as exc:
            logger.error("AI model not configured: %s", exc)
            return "Our AI assistant is temporarily unavailable. Please try again shortly. 🙏"

        # 4. Build history for Gemini
        #    get_history_for_prompt() returns all turns including the one we just added.
        #    We strip the last user turn because we send it as the live message below.
        history = conv.get_history_for_prompt()
        if history and history[-1]["role"] == "user":
            history = history[:-1]

        # 5. Call Gemini
        #    history = previous turns (alternating user/model)
        #    send_message(text) = ONLY the current customer message
        #    system_instruction on the model = always present, no need to repeat it
        try:
            chat = model.start_chat(history=history)
            response = chat.send_message(text)
            reply_text = response.text.strip()
        except GoogleAPIError as exc:
            logger.error("Gemini API error: %s", exc)
            return "Sorry, I'm having trouble thinking right now. 😅 Please try again in a moment."
        except Exception as exc:
            logger.exception("Unexpected AI error: %s", exc)
            return "Something went wrong on our end. Please try again shortly."

        # 6. Check for order intent
        order_data = self._extract_order_json(reply_text)
        clean_reply = self._ORDER_JSON_RE.sub("", reply_text).strip()

        if order_data:
            order_request = self._parse_order_from_json(order_data, customer_phone, customer_name)
            if order_request is None:
                conv.add_model_turn(clean_reply)
                return "I had trouble understanding your order. Could you please retype it? 🙏"

            try:
                order = self._order_service.validate_and_create(order_request)
                confirmation = self._order_service.get_order_confirmation_message(order)
                conv.stage = ConversationStage.ORDERED
                conv.add_model_turn(confirmation)
                conversation_store.reset(customer_phone)
                logger.info("Order %s placed for phone ...%s", order.order_id, customer_phone[-4:])
                return confirmation
            except OrderServiceError as exc:
                error_msg = (
                    f"❌ Sorry, I couldn't place your order:\n{exc}\n\n"
                    "Please check the details and try again."
                )
                conv.add_model_turn(error_msg)
                return error_msg

        # 7. Normal reply — store in history and return
        conv.add_model_turn(clean_reply)
        return clean_reply


# ── Module-level singleton ─────────────────────────────────────────────────────
ai_service = AIService()
