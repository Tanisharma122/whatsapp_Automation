"""
order_models.py — Pydantic models and dataclasses for the order domain.

These models are used across the order service, AI service, and API layer.
They enforce types and validation so bad data is caught before it reaches
Google Sheets or the customer.

Order schema (from actual Orders sheet):
  order_id | customer_name | phone | item_name | quantity | unit_price
  | total_amount | delivery_address | payment_method | order_status | order_date
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OrderStatus(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    PREPARING = "Preparing"
    OUT_FOR_DELIVERY = "Out for Delivery"
    DELIVERED = "Delivered"
    CANCELLED = "Cancelled"


class PaymentMethod(str, Enum):
    UPI = "UPI"
    CASH_ON_DELIVERY = "Cash on Delivery"
    CARD = "Card"


class OrderLineItem(BaseModel):
    """
    A single item line in an order.

    Prices come from the inventory service — never from the AI or the customer.
    """
    item_id: str
    item_name: str
    quantity: int = Field(ge=1, le=50)
    unit_price: float = Field(gt=0)

    @property
    def line_total(self) -> float:
        """Calculate line total in Python — no LLM arithmetic."""
        return round(self.quantity * self.unit_price, 2)


class OrderRequest(BaseModel):
    """
    What the AI service collects from the conversation before placing an order.

    The AI fills these fields through conversation. The order service
    validates them and enriches with real prices from inventory.
    """
    customer_phone: str = Field(description="Customer's WhatsApp phone number")
    customer_name: str = Field(description="Customer's display name")
    items: list[OrderLineItem] = Field(min_length=1)
    delivery_address: str = Field(min_length=3, description="Full delivery address")
    payment_method: PaymentMethod

    @field_validator("customer_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        # WhatsApp numbers should be digits only (E.164 without +)
        if not v.isdigit():
            raise ValueError("Phone number must contain digits only.")
        if len(v) < 10:
            raise ValueError("Phone number is too short.")
        return v

    @field_validator("delivery_address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Delivery address is too short. Please provide a full address.")
        return v

    @property
    def total_amount(self) -> float:
        """Sum of all line totals. Calculated in Python — not by the AI."""
        return round(sum(item.line_total for item in self.items), 2)

    def order_summary_text(self) -> str:
        """Format a readable order summary for sending to the customer."""
        lines = ["📋 *Order Summary*\n"]
        for item in self.items:
            lines.append(
                f"  • {item.item_name} × {item.quantity} = ₹{item.line_total:.0f}"
            )
        lines.append(f"\n*Total: ₹{self.total_amount:.0f}*")
        lines.append(f"📍 Deliver to: {self.delivery_address}")
        lines.append(f"💳 Payment: {self.payment_method.value}")
        return "\n".join(lines)


class Order(BaseModel):
    """
    A completed, persisted order record.

    Created by the order service AFTER all validation passes and the
    row has been successfully written to Google Sheets.
    """
    order_id: str
    customer_name: str
    phone: str
    item_name: str      # comma-joined for multi-item orders
    quantity: str       # comma-joined quantities
    unit_price: str     # comma-joined unit prices
    total_amount: float
    delivery_address: str
    payment_method: str
    order_status: OrderStatus = OrderStatus.PENDING
    order_date: str

    def to_sheet_row(self) -> list:
        """
        Convert this order to a list for appending to Google Sheets.

        Column order MUST match the actual Orders sheet:
        order_id | customer_name | phone | item_name | quantity |
        unit_price | total_amount | delivery_address | payment_method |
        order_status | order_date
        """
        return [
            self.order_id,
            self.customer_name,
            self.phone,
            self.item_name,
            self.quantity,
            self.unit_price,
            self.total_amount,
            self.delivery_address,
            self.payment_method,
            self.order_status.value,
            self.order_date,
        ]
