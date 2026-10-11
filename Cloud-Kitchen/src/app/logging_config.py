"""
logging_config.py — Structured JSON logging with secret redaction.

Why JSON logs?
  Machine-readable logs can be searched, filtered, and sent to tools
  like Datadog or Grafana. In development they are pretty-printed.

Secret redaction:
  We never want a token, API key, or customer phone number written
  to a log file in plain text. The redactor below masks them.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any

from pythonjsonlogger import jsonlogger


# ── Patterns that should NEVER appear in logs ──────────────────────────────────
_REDACT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(access_token\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(bearer\s+)\S+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(password\s*[=:]\s*)\S+", re.IGNORECASE),
    # Mask phone numbers — keep first 4 digits, hide the rest
    re.compile(r"\b(\+?\d{1,3})(\d{6,})\b"),
]


def _redact(text: str) -> str:
    """Replace sensitive patterns with [REDACTED]."""
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs sensitive data from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.msg))
        record.args = tuple(
            _redact(str(a)) if isinstance(a, str) else a
            for a in (record.args or ())
        )
        return True


class RedactingFormatter(jsonlogger.JsonFormatter):
    """JSON formatter that also runs redaction on the final output."""

    def format(self, record: logging.LogRecord) -> str:
        raw = super().format(record)
        return _redact(raw)


def setup_logging(log_level: str = "INFO", pretty: bool = True) -> None:
    """
    Configure root logger.

    Args:
        log_level: One of DEBUG / INFO / WARNING / ERROR.
        pretty:    If True, use a human-readable format (for development).
                   If False, output structured JSON (for production / log tools).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove any handlers that may have been added by imported libraries
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())

    if pretty:
        fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        fmt = RedactingFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
        )

    handler.setFormatter(fmt)
    root.addHandler(handler)
