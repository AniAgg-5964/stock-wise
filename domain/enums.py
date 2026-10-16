"""StockWise — domain enums.

Stored in the database as their string values.
"""

from __future__ import annotations

from enum import Enum


class MovementType(str, Enum):
    """Types of immutable stock movement (the ledger)."""

    OPENING_STOCK = "opening_stock"
    PURCHASE_RECEIPT = "purchase_receipt"
    SALE = "sale"
    RETURN = "return"
    WASTE = "waste"
    ADJUSTMENT = "adjustment"
    CORRECTION = "correction"
    TRANSFER = "transfer"


class StockStatus(str, Enum):
    HEALTHY = "healthy"
    LOW = "low"
    OUT_OF_STOCK = "out_of_stock"
    NEAR_EXPIRY = "near_expiry"
    EXPIRED = "expired"
    AT_RISK = "at_risk"


class RecommendationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class PurchaseOrderStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class SaleSource(str, Enum):
    MANUAL = "manual"
    CSV_IMPORT = "csv_import"
