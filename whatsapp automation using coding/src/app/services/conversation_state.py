"""
conversation_state.py — In-memory conversation state management.

Each customer (identified by their phone number) has their own isolated
conversation history. This state is kept in memory and is NOT shared
between customers.

IMPORTANT LIMITATIONS of in-memory state:
  - State is lost if the server restarts. In production, use Redis or a DB.
  - This is appropriate for a single-server development setup.
  - State automatically expires after MAX_HISTORY_AGE_MINUTES to prevent
    memory growth and stale conversations.

Conversation State Machine:
  GREETING → BROWSING → COLLECTING_ORDER → CONFIRMING → ORDERED

The AI can transition between states based on customer intent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum number of conversation turns to keep in history (to limit token usage)
MAX_HISTORY_TURNS = 20

# Conversation expires after this many minutes of inactivity
MAX_HISTORY_AGE_MINUTES = 60


class ConversationStage(str, Enum):
    """Tracks where in the ordering process the customer is."""
    GREETING = "greeting"         # Just started / no context
    BROWSING = "browsing"         # Looking at menu / asking questions
    COLLECTING_ORDER = "collecting_order"  # AI is collecting order details
    CONFIRMING = "confirming"     # Waiting for customer to say "yes" to summary
    ORDERED = "ordered"           # Order placed successfully


@dataclass
class ConversationTurn:
    """A single exchange in the conversation."""
    role: str   # "user" or "model"
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PendingOrderData:
    """Partial order data collected so far in the conversation."""
    items: list[dict] = field(default_factory=list)   # [{name, qty, price}, ...]
    delivery_address: Optional[str] = None
    payment_method: Optional[str] = None


@dataclass
class CustomerConversation:
    """
    All state for a single customer's conversation.

    Each customer has exactly one of these, keyed by phone number.
    """
    phone: str
    name: str
    stage: ConversationStage = ConversationStage.GREETING
    history: list[ConversationTurn] = field(default_factory=list)
    pending_order: Optional[PendingOrderData] = None
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_user_turn(self, text: str) -> None:
        """Record a message from the customer."""
        self.history.append(ConversationTurn(role="user", text=text))
        self.last_activity = datetime.now(timezone.utc)
        self._trim_history()

    def add_model_turn(self, text: str) -> None:
        """Record a reply from the AI model."""
        self.history.append(ConversationTurn(role="model", text=text))
        self.last_activity = datetime.now(timezone.utc)

    def _trim_history(self) -> None:
        """Keep only the last MAX_HISTORY_TURNS turns to limit token usage."""
        if len(self.history) > MAX_HISTORY_TURNS * 2:
            self.history = self.history[-(MAX_HISTORY_TURNS * 2):]
            logger.debug("Trimmed conversation history for phone %s", self.phone[-4:])

    def is_expired(self) -> bool:
        """Check if this conversation has been inactive too long."""
        age = datetime.now(timezone.utc) - self.last_activity
        return age > timedelta(minutes=MAX_HISTORY_AGE_MINUTES)

    def reset(self) -> None:
        """Clear the conversation and start fresh."""
        self.stage = ConversationStage.GREETING
        self.history = []
        self.pending_order = None
        logger.info("Reset conversation for phone ...%s", self.phone[-4:])

    def get_history_for_prompt(self) -> list[dict[str, str]]:
        """
        Format history as a list of {role, parts} dicts for the Gemini API.

        We use the last MAX_HISTORY_TURNS turns only.
        """
        recent = self.history[-(MAX_HISTORY_TURNS * 2):]
        result = []
        for turn in recent:
            result.append({
                "role": turn.role,
                "parts": [{"text": turn.text}]
            })
        return result


class ConversationStore:
    """
    In-memory store for all active customer conversations.

    Thread-safety note:
      FastAPI runs background tasks in the same event loop but they are
      not truly concurrent (no GIL bypass). This simple dict is safe
      for our use case. For production multi-process deployments, use Redis.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, CustomerConversation] = {}

    def get_or_create(self, phone: str, name: str) -> CustomerConversation:
        """
        Get an existing conversation or create a new one.

        Also cleans up expired conversations on each access.
        """
        self._cleanup_expired()

        if phone not in self._conversations:
            self._conversations[phone] = CustomerConversation(phone=phone, name=name)
            logger.info("New conversation started for phone ...%s", phone[-4:])
        else:
            # Update name in case it changed
            self._conversations[phone].name = name

        return self._conversations[phone]

    def reset(self, phone: str) -> None:
        """Reset a customer's conversation (e.g. after successful order)."""
        if phone in self._conversations:
            self._conversations[phone].reset()

    def _cleanup_expired(self) -> None:
        """Remove expired conversations to free memory."""
        expired = [p for p, conv in self._conversations.items() if conv.is_expired()]
        for phone in expired:
            del self._conversations[phone]
            logger.info("Expired conversation removed for phone ...%s", phone[-4:])

    def active_count(self) -> int:
        """Return the number of active (non-expired) conversations."""
        return sum(1 for conv in self._conversations.values() if not conv.is_expired())


# Module-level singleton — shared across all requests in this process
conversation_store = ConversationStore()
