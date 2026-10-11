"""
idempotency.py — Deduplication tracker for incoming WhatsApp messages.

WHY THIS EXISTS:
  Meta retries webhook delivery if your server doesn't respond with HTTP 200
  quickly enough, or if there's a network hiccup. Without this tracker, the same
  customer message could be processed multiple times, creating duplicate orders.

HOW IT WORKS:
  We keep a set of already-seen message IDs in memory. Before processing a message,
  we check this set. If the ID is already there, we skip it.

LIMITATION:
  This in-memory store is lost if the server restarts. For production, you'd
  replace this with a persistent store (e.g., Redis, a database table).
  We'll upgrade it in Module 5 if needed.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Deque

logger = logging.getLogger(__name__)

# Maximum number of message IDs to remember.
# At ~36 chars per UUID, 10,000 IDs ≈ 360 KB of memory — very small.
_MAX_SIZE = 10_000


class IdempotencyTracker:
    """
    Thread-safe in-memory store for seen message IDs.

    Uses a deque as a bounded FIFO so old IDs are evicted automatically,
    preventing unbounded memory growth.
    """

    def __init__(self, max_size: int = _MAX_SIZE) -> None:
        self._max_size = max_size
        self._seen: set[str] = set()
        self._order: Deque[str] = deque()
        self._lock = threading.Lock()

    def is_duplicate(self, message_id: str) -> bool:
        """
        Return True if this message_id has already been seen.
        If it's new, record it and return False.
        """
        with self._lock:
            if message_id in self._seen:
                logger.debug("Duplicate message detected, skipping id=%s", message_id)
                return True

            # Record the new ID
            self._seen.add(message_id)
            self._order.append(message_id)

            # Evict oldest if over capacity
            if len(self._order) > self._max_size:
                oldest = self._order.popleft()
                self._seen.discard(oldest)

            return False

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def reset(self) -> None:
        """Clear all tracked IDs. Useful in tests."""
        with self._lock:
            self._seen.clear()
            self._order.clear()


# Module-level singleton shared across the application
tracker = IdempotencyTracker()
