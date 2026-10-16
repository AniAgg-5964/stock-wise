"""StockWise — domain policies (pure business rules).

Validation, FEFO ordering, and status derivation. No I/O here.
"""

from __future__ import annotations

from datetime import date

from domain.entities import InventoryBatch, Product
from domain.enums import StockStatus
from domain.exceptions import ValidationError


def is_expired(batch: InventoryBatch, as_of: str | None = None) -> bool:
    """A batch is expired when its expiry date is strictly before ``as_of``."""
    if not batch.expiry_date:
        return False
    reference = as_of or date.today().isoformat()
    return batch.expiry_date < reference


class StockPolicy:
    """Validation and stock-status rules."""

    @staticmethod
    def validate_product_data(product: Product) -> None:
        if not product.sku or not product.sku.strip():
            raise ValidationError("sku", "SKU is required")
        if not product.name or not product.name.strip():
            raise ValidationError("name", "Product name is required")
        if product.cost_price is not None and product.cost_price < 0:
            raise ValidationError("cost_price", "Cost price cannot be negative")
        if product.selling_price is not None and product.selling_price < 0:
            raise ValidationError("selling_price", "Selling price cannot be negative")
        if product.reorder_point < 0:
            raise ValidationError("reorder_point", "Reorder point cannot be negative")
        if product.safety_stock < 0:
            raise ValidationError("safety_stock", "Safety stock cannot be negative")

    @staticmethod
    def validate_positive(value: float | None, field_name: str) -> None:
        if value is None or value <= 0:
            raise ValidationError(field_name, "must be greater than zero")

    @staticmethod
    def derive_status(
        usable_stock: float,
        reorder_point: int,
        *,
        near_expiry: bool = False,
        expired_present: bool = False,
    ) -> StockStatus:
        if usable_stock <= 0:
            return StockStatus.OUT_OF_STOCK
        if expired_present:
            return StockStatus.EXPIRED
        if near_expiry:
            return StockStatus.NEAR_EXPIRY
        if usable_stock <= reorder_point:
            return StockStatus.LOW
        return StockStatus.HEALTHY


def fefo_order(batches: list[InventoryBatch], as_of: str | None = None) -> list[InventoryBatch]:
    """Return consumable batches in First-Expiry-First-Out order.

    Excludes depleted and expired batches. Batches with no expiry date sort last.
    """

    def sort_key(batch: InventoryBatch) -> tuple:
        has_no_expiry = batch.expiry_date is None
        return (has_no_expiry, batch.expiry_date or "", batch.received_at or "", batch.id or 0)

    consumable = [
        b for b in batches if b.quantity_remaining > 0 and not is_expired(b, as_of)
    ]
    return sorted(consumable, key=sort_key)
