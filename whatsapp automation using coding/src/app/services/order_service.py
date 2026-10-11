"""
order_service.py — Creates, validates, and persists orders to Google Sheets.

This is the ONLY place in the application that writes to the Orders sheet.
An order is considered confirmed ONLY when this service successfully
appends a row to the sheet — not when the AI says so.

Duplicate prevention strategy:
  - We generate a unique order_id using a timestamp + phone suffix.
  - Before writing, we check if an order_id already exists in the sheet.
  - If the webhook is retried with the same message, the idempotency tracker
    in message_processor.py prevents the order service from being called twice.
  - Together, these two layers prevent almost all duplicate orders.

Order ID format:
  ORD-YYYYMMDDHHMMSS-XXXX
  where XXXX = last 4 digits of the customer's phone number.
  Example: ORD-20241011142300-3210

Field mapping (actual Orders sheet columns):
  order_id | customer_name | phone | item_name | quantity | unit_price
  | total_amount | delivery_address | payment_method | order_status | order_date
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import settings
from app.integrations.sheets_client import SheetsClient, SheetsClientError
from app.models.order_models import Order, OrderLineItem, OrderRequest, OrderStatus
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)


class OrderServiceError(Exception):
    """Raised when an order cannot be created or validated."""


class OrderService:
    """
    Validates and persists food orders to the Google Sheets Orders sheet.

    Public methods:
        validate_and_create(request) → Order
    """

    def __init__(
        self,
        sheets_client: SheetsClient | None = None,
        inventory_service: InventoryService | None = None,
    ) -> None:
        self._sheets = sheets_client or SheetsClient()
        self._inventory = inventory_service or InventoryService(self._sheets)

    def _get_spreadsheet_id(self) -> str:
        sid = settings.orders_spreadsheet_id
        if not sid:
            raise OrderServiceError("ORDERS_SPREADSHEET_ID is not configured.")
        return sid

    def _get_worksheet_name(self) -> str:
        return settings.orders_worksheet_name or "Orders"

    # ── Order ID generation ────────────────────────────────────────────────────

    @staticmethod
    def _generate_order_id(phone: str) -> str:
        """
        Generate a unique, human-readable order ID.

        Format: ORD-YYYYMMDDHHMMSS-XXXX
        where XXXX = last 4 digits of the phone number.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = phone[-4:] if len(phone) >= 4 else phone.zfill(4)
        return f"ORD-{ts}-{suffix}"

    # ── Duplicate check ────────────────────────────────────────────────────────

    def _order_id_exists(self, order_id: str) -> bool:
        """
        Check if an order with this ID already exists.
        Works with both Google Sheets and local file fallback.
        Returns True if found (duplicate), False if safe to write.
        """
        from app.integrations.excel_data_provider import is_sheets_configured, local_order_store

        if not is_sheets_configured():
            return local_order_store.find_order_by_id(order_id) is not None

        try:
            existing = self._sheets.find_row_by_value(
                spreadsheet_id=self._get_spreadsheet_id(),
                worksheet_name=self._get_worksheet_name(),
                column_header="order_id",
                value=order_id,
            )
            return existing is not None
        except SheetsClientError as exc:
            logger.warning("Could not check for duplicate order ID: %s", exc)
            return False  # proceed and let the write fail if there's a real conflict

    # ── Inventory validation ───────────────────────────────────────────────────

    def _validate_items_against_inventory(
        self, items: list[OrderLineItem]
    ) -> list[str]:
        """
        Verify every item in the order against live inventory.

        Returns a list of human-readable error strings.
        An empty list means all items are valid.

        IMPORTANT: We also re-fetch the unit price from inventory to ensure
        the AI didn't invent or alter the price.
        """
        errors = []
        for item in items:
            available, inv_item, reason = self._inventory.check_availability(
                name=item.item_name, quantity=item.quantity
            )
            if not available:
                errors.append(reason)
            elif inv_item and abs(inv_item.price - item.unit_price) > 0.01:
                # Price mismatch — the AI may have used wrong data
                logger.warning(
                    "Price mismatch for '%s': AI said ₹%.2f, sheet has ₹%.2f — correcting.",
                    item.item_name, item.unit_price, inv_item.price
                )
                # Correct the price in-place
                item.unit_price = inv_item.price
        return errors

    # ── Order creation ─────────────────────────────────────────────────────────

    def validate_and_create(self, request: OrderRequest) -> Order:
        """
        Validate an order request and, if valid, write it to the Orders sheet.

        This is the authoritative order-creation path. An order is only
        confirmed when this method returns successfully.

        Args:
            request: A fully populated OrderRequest from the AI service.

        Returns:
            The created Order with its assigned order_id.

        Raises:
            OrderServiceError: If validation fails or the sheet write fails.
        """
        logger.info(
            "Creating order for customer phone=...%s, items=%d",
            request.customer_phone[-4:], len(request.items)
        )

        # Step 1: Validate items against live inventory (also corrects prices)
        validation_errors = self._validate_items_against_inventory(request.items)
        if validation_errors:
            raise OrderServiceError(
                "Order validation failed:\n" + "\n".join(f"• {e}" for e in validation_errors)
            )

        # Step 2: Calculate total in Python (never trust AI arithmetic)
        total = request.total_amount
        logger.info("Order total calculated: ₹%.2f", total)

        # Step 3: Generate order ID and check for duplicates
        order_id = self._generate_order_id(request.customer_phone)
        if self._order_id_exists(order_id):
            # Extremely rare (same second, same phone last 4 digits)
            # Add a microsecond suffix to make it unique
            import time as _time
            micro_suffix = str(int(_time.time() * 1000000) % 1000).zfill(3)
            order_id = order_id + "-" + micro_suffix
            logger.warning("Order ID collision detected — generated new ID: %s", order_id)

        # Step 4: Build the Order object
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # For multi-item orders, join fields with commas
        item_names = ", ".join(item.item_name for item in request.items)
        quantities = ", ".join(str(item.quantity) for item in request.items)
        unit_prices = ", ".join(f"{item.unit_price:.2f}" for item in request.items)

        order = Order(
            order_id=order_id,
            customer_name=request.customer_name,
            phone=request.customer_phone,
            item_name=item_names,
            quantity=quantities,
            unit_price=unit_prices,
            total_amount=total,
            delivery_address=request.delivery_address,
            payment_method=request.payment_method.value,
            order_status=OrderStatus.PENDING,
            order_date=now_str,
        )

        # Step 5: Write to Google Sheets (or local fallback)
        from app.integrations.excel_data_provider import is_sheets_configured, local_order_store

        if not is_sheets_configured():
            # Local file fallback
            try:
                local_order_store.append_order(order.to_sheet_row())
                logger.info("Order %s saved to local file (Sheets not configured).", order_id)
            except Exception as exc:
                logger.error("Failed to write order %s to local file: %s", order_id, exc)
                raise OrderServiceError(
                    f"Could not save your order. Please try again. (Reference: {order_id})"
                ) from exc
        else:
            try:
                self._sheets.append_row(
                    spreadsheet_id=self._get_spreadsheet_id(),
                    worksheet_name=self._get_worksheet_name(),
                    row=order.to_sheet_row(),
                )
            except SheetsClientError as exc:
                logger.error("Failed to write order %s to sheet: %s", order_id, exc)
                raise OrderServiceError(
                    f"Could not save your order to our system. Please try again. (Reference: {order_id})"
                ) from exc

        logger.info(
            "Order %s created successfully. Total: ₹%.2f, Items: %s",
            order_id, total, item_names
        )
        return order

    def get_order_confirmation_message(self, order: Order) -> str:
        """
        Format the order confirmation message to send to the customer.

        This is called ONLY after validate_and_create() returns successfully.
        """
        return (
            f"✅ *Order Confirmed!*\n\n"
            f"🆔 Order ID: `{order.order_id}`\n"
            f"🍽️ Items: {order.item_name}\n"
            f"💰 Total: ₹{order.total_amount:.0f}\n"
            f"📍 Delivery to: {order.delivery_address}\n"
            f"💳 Payment: {order.payment_method}\n"
            f"⏱️ Status: {order.order_status.value}\n\n"
            f"Thank you for ordering from Cloud Kitchen! 🙏\n"
            f"We'll start preparing your order shortly."
        )
