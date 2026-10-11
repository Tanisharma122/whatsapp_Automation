"""
faq_service.py — Reads and searches the FAQ data from Google Sheets.

IMPORTANT NOTE about the FAQ sheet format:
  The 'faqs' worksheet in Food_Delivery_System.xlsx has a special format:
  ALL data is stored in a SINGLE column (column A), with each row containing
  all fields as a space-separated string:

    Row 1 (header): "faq_id question keywords answer category active"
    Row 2+: "FAQ001 What are your delivery hours? delivery hours, ... answer text Category Yes"

  This appears to be a Google Sheets export where columns got merged.
  We parse it by splitting on the field separator pattern.

  The Google Sheets live version may have proper columns. We support both:
  - If the sheet has multiple columns (proper format), we use get_all_records().
  - If it's single-column (merged export), we parse each row by splitting.

Field mapping (from actual faqs sheet):
  faq_id | question | keywords | answer | category | active
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.integrations.sheets_client import SheetsClient, SheetsClientError

logger = logging.getLogger(__name__)

# Known FAQ IDs in the format "FAQ001", "FAQ002" etc.
_FAQ_ID_PATTERN = re.compile(r'^FAQ\d{3}', re.IGNORECASE)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class FAQ:
    """Represents a single FAQ entry."""
    faq_id: str
    question: str
    keywords: list[str]   # list of keyword phrases
    answer: str
    category: str
    active: bool

    @classmethod
    def from_sheet_row(cls, row: dict[str, Any]) -> Optional["FAQ"]:
        """
        Build a FAQ from a properly-formatted multi-column row dict.
        Returns None if the row is missing required fields.
        """
        faq_id = str(row.get("faq_id", "")).strip()
        question = str(row.get("question", "")).strip()
        answer = str(row.get("answer", "")).strip()
        if not faq_id or not question or not answer:
            return None

        keywords_raw = str(row.get("keywords", "")).strip()
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

        active_raw = str(row.get("active", "Yes")).strip().lower()
        return cls(
            faq_id=faq_id,
            question=question,
            keywords=keywords,
            answer=answer,
            category=str(row.get("category", "")).strip(),
            active=active_raw == "yes",
        )

    @classmethod
    def from_single_column_row(cls, raw: str) -> Optional["FAQ"]:
        """
        Parse a FAQ from the single-column format found in the downloaded sheet.

        Each row looks like:
          "FAQ001 What are your delivery hours? delivery hours, ... answer text Category Yes"

        We use the FAQ ID at the start, "Yes" or "No" at the end, and
        heuristics to split the middle fields.
        """
        raw = raw.strip()
        if not _FAQ_ID_PATTERN.match(raw):
            return None  # skip header or malformed rows

        # Split off the FAQ ID
        parts = raw.split(" ", 1)
        if len(parts) < 2:
            return None
        faq_id = parts[0]
        rest = parts[1]

        # The last word should be "Yes" or "No" (active flag)
        words = rest.rsplit(" ", 1)
        if len(words) < 2:
            return None
        active_str = words[1].strip().lower()
        if active_str not in ("yes", "no"):
            active_str = "yes"
            rest_without_active = rest
        else:
            rest_without_active = words[0]

        # The last word before active is the category (single word: Delivery, Menu, etc.)
        rest_parts = rest_without_active.rsplit(" ", 1)
        if len(rest_parts) < 2:
            return None
        category = rest_parts[1].strip()
        content = rest_parts[0]

        # Now we need to split question | keywords | answer
        # Strategy: question ends at "?" — everything before the first "?" is the question
        q_split = content.split("?", 1)
        if len(q_split) < 2:
            # No question mark — use whole content as question, no keywords
            return cls(
                faq_id=faq_id,
                question=content.strip(),
                keywords=[],
                answer="",
                category=category,
                active=(active_str == "yes"),
            )

        question = q_split[0].strip() + "?"
        after_q = q_split[1].strip()

        # Keywords are comma-separated and precede the answer text.
        # Heuristic: keywords section runs until a non-comma-separated word
        # We detect the answer as text after the last keyword phrase.
        # Simple approach: find first full sentence (ends in ".") as answer start.
        # Split at first capital letter after a non-keyword character run.
        # Better: find where keywords end by looking for sentences
        answer_match = re.search(r'\b[A-Z][a-z].*[.!]', after_q)
        if answer_match:
            keywords_str = after_q[:answer_match.start()].strip()
            answer = after_q[answer_match.start():].strip()
        else:
            # Fallback: everything is the answer
            keywords_str = ""
            answer = after_q

        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

        return cls(
            faq_id=faq_id,
            question=question,
            keywords=keywords,
            answer=answer,
            category=category,
            active=(active_str == "yes"),
        )

    def matches_query(self, query: str) -> bool:
        """
        Check if this FAQ is relevant to a customer query.

        Matches against the question and keywords (case-insensitive).
        """
        query_lower = query.lower()
        # Check question words
        if any(word in self.question.lower() for word in query_lower.split() if len(word) > 2):
            return True
        # Check keywords
        for kw in self.keywords:
            if kw.lower() in query_lower or query_lower in kw.lower():
                return True
        return False


# ── Service ───────────────────────────────────────────────────────────────────

class FAQService:
    """
    Provides FAQ queries backed by the live Google Sheets FAQ sheet.

    Handles both the proper multi-column format and the single-column
    merged-export format found in the downloaded file.
    """

    def __init__(self, sheets_client: Optional[SheetsClient] = None) -> None:
        self._sheets = sheets_client or SheetsClient()

    def _get_spreadsheet_id(self) -> str:
        sid = settings.faq_spreadsheet_id
        if not sid:
            raise SheetsClientError("FAQ_SPREADSHEET_ID is not configured.")
        return sid

    def _get_worksheet_name(self) -> str:
        return settings.faq_worksheet_name or "faqs"

    def get_all_faqs(self) -> list[FAQ]:
        """
        Fetch all active FAQs from the sheet.

        Automatically detects and handles both single-column and
        multi-column sheet formats.

        Returns:
            List of active FAQ objects.

        Raises:
            SheetsClientError on sheet access failure.
        """
        # First, try multi-column format (proper Google Sheets)
        try:
            raw_rows = self._sheets.read_all_records(
                spreadsheet_id=self._get_spreadsheet_id(),
                worksheet_name=self._get_worksheet_name(),
            )

            # Check if we got proper columns or single-column merged data
            if raw_rows and len(raw_rows[0]) > 1:
                # Proper multi-column format
                faqs = []
                for row in raw_rows:
                    faq = FAQ.from_sheet_row(row)
                    if faq and faq.active:
                        faqs.append(faq)
                logger.info("Loaded %d FAQs (multi-column format).", len(faqs))
                return faqs
            else:
                # Single-column format — parse as raw column
                return self._load_single_column_faqs()

        except SheetsClientError:
            raise

    def _load_single_column_faqs(self) -> list[FAQ]:
        """Parse FAQs from single-column format."""
        raw_values = self._sheets.read_raw_column(
            spreadsheet_id=self._get_spreadsheet_id(),
            worksheet_name=self._get_worksheet_name(),
            col=1,
        )
        faqs = []
        for i, raw in enumerate(raw_values):
            if i == 0:  # skip header row
                continue
            if not raw or not raw.strip():
                continue
            faq = FAQ.from_single_column_row(raw)
            if faq and faq.active:
                faqs.append(faq)
        logger.info("Loaded %d FAQs (single-column format).", len(faqs))
        return faqs

    def find_answer(self, query: str) -> Optional[str]:
        """
        Find the best FAQ answer for a customer query.

        Returns:
            The FAQ answer string, or None if no FAQ matches.
        """
        try:
            faqs = self.get_all_faqs()
        except SheetsClientError as exc:
            logger.error("Could not load FAQs: %s", exc)
            return None

        # Find all matching FAQs
        matches = [faq for faq in faqs if faq.matches_query(query)]
        if not matches:
            return None

        # Return the first match (could be improved with scoring in the future)
        best = matches[0]
        logger.info("FAQ match: %s for query (length=%d)", best.faq_id, len(query))
        return best.answer

    def get_all_as_context(self) -> str:
        """
        Format all active FAQs as a single string for injecting into an LLM prompt.

        This gives the AI model full knowledge of all FAQs without having to
        make a separate API call for each customer question.
        """
        try:
            faqs = self.get_all_faqs()
        except SheetsClientError as exc:
            logger.error("Could not load FAQs for context: %s", exc)
            return ""

        if not faqs:
            return ""

        lines = []
        for faq in faqs:
            lines.append(f"Q: {faq.question}")
            lines.append(f"A: {faq.answer}")
            lines.append("")

        return "\n".join(lines)
