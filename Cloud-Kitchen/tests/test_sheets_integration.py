"""
test_sheets_integration.py — Module 3 tests: Google Sheets integration and business logic.

ALL external API calls are mocked. These tests:
  - Verify inventory parsing with real schema column names.
  - Verify FAQ parsing with both single-column and multi-column formats.
  - Verify order validation logic (availability, price correction).
  - Verify order total calculations.
  - Verify order ID generation format.
  - Verify the to_sheet_row() column order matches the actual Orders sheet.

No real Google Sheets API calls are made here.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.services.inventory_service import InventoryItem, InventoryService
from app.services.faq_service import FAQ, FAQService
from app.services.order_service import OrderService, OrderServiceError
from app.models.order_models import OrderLineItem, OrderRequest, PaymentMethod


# ── Fixtures — sample data matching actual sheet schema ───────────────────────

SAMPLE_INVENTORY_ROWS = [
    {
        "item_id": "I001", "item_name": "Margherita Pizza",
        "description": "Classic pizza with tomato, mozzarella, and basil",
        "category": "Pizza", "price": 249.0, "available": "Yes", "quantity": 20
    },
    {
        "item_id": "I002", "item_name": "Farmhouse Pizza",
        "description": "Pizza topped with onion, capsicum, tomato, and mushrooms",
        "category": "Pizza", "price": 329.0, "available": "Yes", "quantity": 15
    },
    {
        "item_id": "I003", "item_name": "Veg Burger",
        "description": "Crispy vegetable patty with lettuce and house sauce",
        "category": "Burger", "price": 149.0, "available": "Yes", "quantity": 25
    },
    {
        "item_id": "I004", "item_name": "Paneer Tikka Wrap",
        "description": "Paneer tikka, fresh vegetables, and mint sauce in a wrap",
        "category": "Wraps", "price": 179.0, "available": "Yes", "quantity": 18
    },
    {
        "item_id": "I005", "item_name": "French Fries",
        "description": "Golden crispy salted fries",
        "category": "Sides", "price": 99.0, "available": "Yes", "quantity": 30
    },
    {
        "item_id": "I010", "item_name": "Veg Cheese Sandwich",
        "description": "Grilled sandwich with vegetables and cheese",
        "category": "Sandwiches", "price": 139.0, "available": "No", "quantity": 0
    },
]

SAMPLE_FAQ_ROWS = [
    {
        "faq_id": "FAQ001", "question": "What are your delivery hours?",
        "keywords": "delivery hours, opening time, delivery time",
        "answer": "We accept orders during our operating hours.",
        "category": "Delivery", "active": "Yes"
    },
    {
        "faq_id": "FAQ003", "question": "What payment methods are accepted?",
        "keywords": "payment, cash, online payment, UPI",
        "answer": "We accept UPI, Cash on Delivery, and Card payments.",
        "category": "Payment", "active": "Yes"
    },
    {
        "faq_id": "FAQ013", "question": "Do you offer vegetarian food?",
        "keywords": "vegetarian, veg food, veg menu",
        "answer": "Yes, vegetarian items are available when listed on the current menu.",
        "category": "Menu", "active": "Yes"
    },
    {
        "faq_id": "FAQ_INACTIVE", "question": "Old inactive question",
        "keywords": "old",
        "answer": "Old answer",
        "category": "Other", "active": "No"  # Should be filtered out
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3A — InventoryItem parsing
# ══════════════════════════════════════════════════════════════════════════════

class TestInventoryItemParsing:
    """Test that InventoryItem correctly parses sheet row dicts."""

    def test_parse_available_item(self):
        row = SAMPLE_INVENTORY_ROWS[0]  # Margherita Pizza
        item = InventoryItem.from_sheet_row(row)
        assert item.item_id == "I001"
        assert item.item_name == "Margherita Pizza"
        assert item.price == 249.0
        assert item.available is True
        assert item.quantity == 20

    def test_parse_unavailable_item(self):
        row = SAMPLE_INVENTORY_ROWS[5]  # Veg Cheese Sandwich — No
        item = InventoryItem.from_sheet_row(row)
        assert item.available is False
        assert item.quantity == 0
        assert item.is_orderable() is False

    def test_is_orderable_sufficient_stock(self):
        row = SAMPLE_INVENTORY_ROWS[2]  # Veg Burger, qty=25
        item = InventoryItem.from_sheet_row(row)
        assert item.is_orderable(requested_qty=10) is True

    def test_is_orderable_insufficient_stock(self):
        row = SAMPLE_INVENTORY_ROWS[2]  # Veg Burger, qty=25
        item = InventoryItem.from_sheet_row(row)
        assert item.is_orderable(requested_qty=30) is False

    def test_price_is_float(self):
        for row in SAMPLE_INVENTORY_ROWS:
            item = InventoryItem.from_sheet_row(row)
            assert isinstance(item.price, float)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3B — InventoryService (mocked sheet)
# ══════════════════════════════════════════════════════════════════════════════

class TestInventoryService:
    """Test InventoryService with a mocked SheetsClient."""

    @pytest.fixture
    def mock_sheets(self):
        mock = MagicMock()
        mock.read_all_records.return_value = SAMPLE_INVENTORY_ROWS
        return mock

    @pytest.fixture
    def service(self, mock_sheets):
        return InventoryService(sheets_client=mock_sheets)

    def test_get_all_items_count(self, service):
        items = service.get_all_items()
        assert len(items) == 6

    def test_get_available_items_filters_unavailable(self, service):
        available = service.get_available_items()
        names = [i.item_name for i in available]
        assert "Veg Cheese Sandwich" not in names
        assert "Margherita Pizza" in names

    def test_find_item_by_name_exact(self, service):
        item = service.find_item_by_name("Margherita Pizza")
        assert item is not None
        assert item.item_id == "I001"
        assert item.price == 249.0

    def test_find_item_by_name_case_insensitive(self, service):
        item = service.find_item_by_name("margherita pizza")
        assert item is not None
        assert item.item_name == "Margherita Pizza"

    def test_find_item_by_name_partial(self, service):
        item = service.find_item_by_name("Burger")
        assert item is not None
        assert item.item_name == "Veg Burger"

    def test_find_item_by_name_not_found(self, service):
        item = service.find_item_by_name("Alien Food")
        assert item is None

    def test_check_availability_available_item(self, service):
        ok, item, reason = service.check_availability("French Fries", quantity=2)
        assert ok is True
        assert item is not None
        assert item.price == 99.0
        assert reason == ""

    def test_check_availability_not_on_menu(self, service):
        ok, item, reason = service.check_availability("Sushi Roll")
        assert ok is False
        assert item is None
        assert "not on our menu" in reason

    def test_check_availability_item_unavailable(self, service):
        ok, item, reason = service.check_availability("Veg Cheese Sandwich")
        assert ok is False
        assert "unavailable" in reason.lower()

    def test_format_menu_contains_available_items(self, service):
        menu = service.format_menu()
        assert "Margherita Pizza" in menu
        assert "₹249" in menu
        # Unavailable items should not appear
        assert "Veg Cheese Sandwich" not in menu

    def test_format_menu_has_categories(self, service):
        menu = service.format_menu()
        assert "Pizza" in menu
        assert "Burger" in menu


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3C — FAQ parsing and FAQService
# ══════════════════════════════════════════════════════════════════════════════

class TestFAQParsing:
    """Test FAQ parsing from both formats."""

    def test_parse_multi_column_row(self):
        row = SAMPLE_FAQ_ROWS[0]
        faq = FAQ.from_sheet_row(row)
        assert faq is not None
        assert faq.faq_id == "FAQ001"
        assert faq.active is True
        assert "delivery hours" in faq.keywords

    def test_inactive_faq_marked_correctly(self):
        row = SAMPLE_FAQ_ROWS[3]  # active = "No"
        faq = FAQ.from_sheet_row(row)
        assert faq is not None
        assert faq.active is False

    def test_faq_matches_query_by_keyword(self):
        faq = FAQ.from_sheet_row(SAMPLE_FAQ_ROWS[0])
        assert faq.matches_query("What are your delivery hours?") is True

    def test_faq_no_match(self):
        faq = FAQ.from_sheet_row(SAMPLE_FAQ_ROWS[0])
        # This FAQ is about delivery hours — shouldn't match pizza questions
        assert faq.matches_query("Can I get a refund?") is False

    def test_single_column_row_parsing(self):
        raw = (
            "FAQ001 What are your delivery hours? delivery hours, opening time, delivery time "
            "We accept orders during our operating hours. Delivery Yes"
        )
        faq = FAQ.from_single_column_row(raw)
        assert faq is not None
        assert faq.faq_id == "FAQ001"
        assert faq.active is True


class TestFAQService:
    """Test FAQService with a mocked SheetsClient."""

    @pytest.fixture
    def mock_sheets_multi_col(self):
        mock = MagicMock()
        mock.read_all_records.return_value = SAMPLE_FAQ_ROWS
        return mock

    @pytest.fixture
    def service(self, mock_sheets_multi_col):
        return FAQService(sheets_client=mock_sheets_multi_col)

    def test_get_all_faqs_filters_inactive(self, service):
        faqs = service.get_all_faqs()
        ids = [f.faq_id for f in faqs]
        assert "FAQ_INACTIVE" not in ids

    def test_find_answer_payment(self, service):
        answer = service.find_answer("what payment methods do you accept")
        assert answer is not None
        assert len(answer) > 0

    def test_find_answer_no_match(self, service):
        answer = service.find_answer("xyzzy frobnotz")
        assert answer is None

    def test_get_all_as_context_returns_string(self, service):
        ctx = service.get_all_as_context()
        assert isinstance(ctx, str)
        assert "FAQ001" not in ctx  # IDs aren't shown to customer
        assert "delivery hours" in ctx.lower() or "operating hours" in ctx.lower()


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3D — OrderLineItem and total calculation
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderCalculations:
    """Verify that totals are calculated correctly in Python code."""

    def test_line_total_single_item(self):
        item = OrderLineItem(item_id="I001", item_name="Margherita Pizza", quantity=2, unit_price=249.0)
        assert item.line_total == 498.0

    def test_line_total_rounding(self):
        item = OrderLineItem(item_id="I008", item_name="Masala Chai", quantity=3, unit_price=40.0)
        assert item.line_total == 120.0

    def test_order_total_multiple_items(self):
        request = OrderRequest(
            customer_phone="919876543210",
            customer_name="Test Customer",
            items=[
                OrderLineItem(item_id="I001", item_name="Margherita Pizza", quantity=2, unit_price=249.0),
                OrderLineItem(item_id="I005", item_name="French Fries", quantity=1, unit_price=99.0),
            ],
            delivery_address="123 Test Street, Ahmedabad",
            payment_method=PaymentMethod.UPI,
        )
        # 2×249 + 1×99 = 498 + 99 = 597
        assert request.total_amount == 597.0

    def test_order_summary_contains_total(self):
        request = OrderRequest(
            customer_phone="919876543210",
            customer_name="Test",
            items=[
                OrderLineItem(item_id="I003", item_name="Veg Burger", quantity=1, unit_price=149.0),
            ],
            delivery_address="Test Road",
            payment_method=PaymentMethod.CASH_ON_DELIVERY,
        )
        summary = request.order_summary_text()
        assert "₹149" in summary
        assert "Veg Burger" in summary


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3E — OrderService validation and creation
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderService:
    """Test OrderService with mocked SheetsClient and InventoryService."""

    @pytest.fixture
    def mock_sheets(self):
        mock = MagicMock()
        # No existing orders (for duplicate check)
        mock.read_all_records.return_value = []
        mock.find_row_by_value.return_value = None  # no duplicates
        mock.append_row.return_value = None  # success
        return mock

    @pytest.fixture
    def mock_inventory(self):
        mock = MagicMock()
        # Default: item available at correct price
        mock.check_availability.return_value = (
            True,
            InventoryItem(
                item_id="I001", item_name="Margherita Pizza",
                description="", category="Pizza",
                price=249.0, available=True, quantity=20
            ),
            ""
        )
        return mock

    @pytest.fixture
    def service(self, mock_sheets, mock_inventory):
        svc = OrderService(sheets_client=mock_sheets, inventory_service=mock_inventory)
        return svc

    @pytest.fixture
    def valid_request(self):
        return OrderRequest(
            customer_phone="919876543210",
            customer_name="Riya Sharma",
            items=[
                OrderLineItem(item_id="I001", item_name="Margherita Pizza", quantity=2, unit_price=249.0),
            ],
            delivery_address="10 MG Road, Ahmedabad",
            payment_method=PaymentMethod.UPI,
        )

    def test_create_order_returns_order(self, service, valid_request):
        order = service.validate_and_create(valid_request)
        assert order.order_id.startswith("ORD-")
        assert order.total_amount == 498.0
        assert order.order_status.value == "Pending"

    def test_order_id_format(self, service, valid_request):
        order = service.validate_and_create(valid_request)
        # ORD-YYYYMMDDHHMMSS-XXXX  (or with collision suffix: ORD-YYYYMMDDHHMMSS-XXXX-NNN)
        parts = order.order_id.split("-")
        assert parts[0] == "ORD"
        assert len(parts[1]) == 14  # YYYYMMDDHHMMSS
        assert len(parts[2]) == 4   # last 4 digits of phone

    def test_sheet_append_called_once(self, service, mock_sheets, valid_request):
        service.validate_and_create(valid_request)
        mock_sheets.append_row.assert_called_once()

    def test_sheet_row_column_order(self, service, mock_sheets, valid_request):
        """The row passed to append_row must match the actual Orders sheet column order."""
        service.validate_and_create(valid_request)
        call_args = mock_sheets.append_row.call_args
        row = call_args.kwargs.get("row") or call_args[1].get("row") or call_args[0][2]
        # Expected column order: order_id, customer_name, phone, item_name,
        # quantity, unit_price, total_amount, delivery_address, payment_method,
        # order_status, order_date
        assert len(row) == 11
        assert row[0].startswith("ORD-")   # order_id
        assert row[1] == "Riya Sharma"      # customer_name
        assert row[2] == "919876543210"     # phone
        assert row[3] == "Margherita Pizza" # item_name
        assert row[4] == "2"                # quantity (str)
        assert "249" in str(row[5])         # unit_price
        assert row[6] == 498.0              # total_amount
        assert row[9] == "Pending"          # order_status

    def test_unavailable_item_raises_error(self, mock_sheets):
        mock_inv = MagicMock()
        mock_inv.check_availability.return_value = (
            False, None, "Sorry, 'Alien Food' is not on our menu."
        )
        service = OrderService(sheets_client=mock_sheets, inventory_service=mock_inv)

        request = OrderRequest(
            customer_phone="919999999999",
            customer_name="Test",
            items=[
                OrderLineItem(item_id="X", item_name="Alien Food", quantity=1, unit_price=100.0),
            ],
            delivery_address="Some Address",
            payment_method=PaymentMethod.UPI,
        )
        with pytest.raises(OrderServiceError) as exc_info:
            service.validate_and_create(request)
        assert "not on our menu" in str(exc_info.value)

    def test_sheet_write_failure_raises_order_service_error(self, mock_sheets, mock_inventory, valid_request):
        from app.integrations.sheets_client import SheetsClientError
        mock_sheets.append_row.side_effect = SheetsClientError("Quota exceeded")
        service = OrderService(sheets_client=mock_sheets, inventory_service=mock_inventory)

        with pytest.raises(OrderServiceError) as exc_info:
            service.validate_and_create(valid_request)
        assert "Could not save" in str(exc_info.value)

    def test_price_correction_when_ai_sends_wrong_price(self, mock_sheets):
        """If the AI sends a wrong price, the service corrects it from inventory."""
        mock_inv = MagicMock()
        correct_item = InventoryItem(
            item_id="I001", item_name="Margherita Pizza",
            description="", category="Pizza",
            price=249.0, available=True, quantity=20
        )
        mock_inv.check_availability.return_value = (True, correct_item, "")
        service = OrderService(sheets_client=mock_sheets, inventory_service=mock_inv)

        # AI sent wrong price (500 instead of 249)
        request = OrderRequest(
            customer_phone="919876543210",
            customer_name="Test",
            items=[
                OrderLineItem(item_id="I001", item_name="Margherita Pizza", quantity=1, unit_price=500.0),
            ],
            delivery_address="Test Address",
            payment_method=PaymentMethod.UPI,
        )
        order = service.validate_and_create(request)
        # Total should be 249 (corrected), not 500 (wrong AI price)
        assert order.total_amount == 249.0

    def test_confirmation_message_format(self, service, valid_request):
        order = service.validate_and_create(valid_request)
        msg = service.get_order_confirmation_message(order)
        assert "✅" in msg
        assert "Order Confirmed" in msg
        assert order.order_id in msg
        assert "₹498" in msg
