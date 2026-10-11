"""
inventory_service.py — Reads and queries the inventory from Google Sheets.

This service is the ONLY place in the application that talks to the inventory
data. All other modules (AI, order service) ask this service for item info.

WHY we don't let the LLM calculate prices:
  LLMs can hallucinate numbers. We ALWAYS read prices from the real inventory
  sheet and do all arithmetic in plain Python. The AI only chooses WHICH item
  the customer wants — not what it costs.

Field mapping (from actual Inventory sheet):
  item_id   | item_name | description | category | price | available | quantity
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.integrations.sheets_client import SheetsClient, SheetsClientError

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class InventoryItem:
    """Represents a single item in the inventory."""
    item_id: str
    item_name: str
    description: str
    category: str
    price: float           # in Indian Rupees (₹)
    available: bool        # True if the item can be ordered
    quantity: int          # stock quantity remaining

    @classmethod
    def from_sheet_row(cls, row: dict[str, Any]) -> "InventoryItem":
        """
        Build an InventoryItem from a raw row dict returned by gspread.

        All field names match the actual column headers in the Inventory sheet.
        """
        # available column is "Yes" / "No" (case-insensitive)
        available_raw = str(row.get("available", "No")).strip().lower()
        return cls(
            item_id=str(row.get("item_id", "")).strip(),
            item_name=str(row.get("item_name", "")).strip(),
            description=str(row.get("description", "")).strip(),
            category=str(row.get("category", "")).strip(),
            price=float(row.get("price", 0) or 0),
            available=available_raw == "yes",
            quantity=int(float(row.get("quantity", 0) or 0)),
        )

    def is_orderable(self, requested_qty: int = 1) -> bool:
        """Return True only if item is available AND has sufficient stock."""
        return self.available and self.quantity >= requested_qty

    def to_customer_description(self) -> str:
        """Return a human-readable string for the customer."""
        status = "✅ Available" if self.is_orderable() else "❌ Unavailable"
        return (
            f"*{self.item_name}* — ₹{self.price:.0f}\n"
            f"  {self.description}\n"
            f"  Category: {self.category} | {status}"
        )


# ── Service ───────────────────────────────────────────────────────────────────

class InventoryService:
    """
    Provides inventory queries backed by the live Google Sheets inventory sheet.

    All reads go through SheetsClient. This service adds domain logic on top
    (item lookup by name, availability checks, menu formatting).
    """

    def __init__(self, sheets_client: Optional[SheetsClient] = None) -> None:
        self._sheets = sheets_client or SheetsClient()

    def _get_spreadsheet_id(self) -> str:
        sid = settings.inventory_spreadsheet_id
        if not sid:
            raise SheetsClientError(
                "INVENTORY_SPREADSHEET_ID is not configured."
            )
        return sid

    def _get_worksheet_name(self) -> str:
        return settings.inventory_worksheet_name or "Inventory"

    # ── Public API ────────────────────────────────────────────────────────────

    def get_all_items(self) -> list[InventoryItem]:
        """
        Fetch and return all inventory items.

        Tries Google Sheets first. If not configured, falls back to the
        local Excel file (data/Food_Delivery_System.xlsx).

        Returns:
            List of InventoryItem objects. Empty list if no data source available.
        """
        # Try local Excel fallback first if Sheets is not configured
        from app.integrations.excel_data_provider import is_sheets_configured, excel_provider

        if not is_sheets_configured():
            logger.info("Google Sheets not configured — using local Excel fallback.")
            raw_rows = excel_provider.read_inventory()
            items = [InventoryItem.from_sheet_row(row) for row in raw_rows]
            logger.info("Loaded %d inventory items from Excel.", len(items))
            return items

        # Google Sheets path
        raw_rows = self._sheets.read_all_records(
            spreadsheet_id=self._get_spreadsheet_id(),
            worksheet_name=self._get_worksheet_name(),
        )
        items = [InventoryItem.from_sheet_row(row) for row in raw_rows]
        logger.info("Loaded %d inventory items from Google Sheets.", len(items))
        return items

    def get_available_items(self) -> list[InventoryItem]:
        """Return only items that are currently available and in stock."""
        return [item for item in self.get_all_items() if item.is_orderable()]

    def find_item_by_name(self, name: str) -> Optional[InventoryItem]:
        """
        Case-insensitive fuzzy lookup of an item by name.

        Tries exact match first, then a case-insensitive contains check.

        Args:
            name: The item name to search for (as understood from the customer).

        Returns:
            The matching InventoryItem, or None if not found.
        """
        name_lower = name.lower().strip()
        all_items = self.get_all_items()

        # 1. Exact match (case-insensitive)
        for item in all_items:
            if item.item_name.lower() == name_lower:
                return item

        # 2. Contains match
        for item in all_items:
            if name_lower in item.item_name.lower():
                return item

        return None

    def find_item_by_id(self, item_id: str) -> Optional[InventoryItem]:
        """Look up an item by its unique item_id (e.g. 'I001')."""
        for item in self.get_all_items():
            if item.item_id.upper() == item_id.upper():
                return item
        return None

    def check_availability(self, name: str, quantity: int = 1) -> tuple[bool, Optional[InventoryItem], str]:
        """
        Check if an item is available in the requested quantity.

        Returns:
            (available: bool, item: InventoryItem | None, reason: str)
              - If available=True, item is the matching InventoryItem.
              - If available=False, reason explains why (not found / unavailable / low stock).
        """
        item = self.find_item_by_name(name)
        if item is None:
            return False, None, f"Sorry, '{name}' is not on our menu."
        if not item.available:
            return False, item, f"Sorry, *{item.item_name}* is currently unavailable."
        if item.quantity < quantity:
            if item.quantity == 0:
                return False, item, f"Sorry, *{item.item_name}* is out of stock."
            return False, item, (
                f"Sorry, we only have {item.quantity} of *{item.item_name}* left, "
                f"but you requested {quantity}."
            )
        return True, item, ""

    def format_menu(self) -> str:
        """
        Return a formatted menu string for sending to the customer.

        Groups items by category. Only shows available items.
        Prices are read directly from the sheet — never invented.
        """
        items = self.get_available_items()
        if not items:
            return "Our menu is currently unavailable. Please try again later."

        # Group by category
        categories: dict[str, list[InventoryItem]] = {}
        for item in items:
            categories.setdefault(item.category, []).append(item)

        lines = ["🍽️ *Our Menu*\n"]
        for category, cat_items in categories.items():
            lines.append(f"*{category}*")
            for item in cat_items:
                lines.append(f"  • {item.item_name} — ₹{item.price:.0f}")
                if item.description:
                    lines.append(f"    _{item.description}_")
            lines.append("")

        lines.append("_Prices are in Indian Rupees (₹). Type an item name to order._")
        return "\n".join(lines)
