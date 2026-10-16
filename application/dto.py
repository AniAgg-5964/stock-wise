"""StockWise — data-transfer objects shared between services and the UI.

These are plain, read-only-ish containers. They never touch the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.entities import InventoryBatch, Product, StockMovement


@dataclass
class ImportRowError:
    """A single invalid row in an imported file."""

    row_number: int
    field: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"Row {self.row_number} ({self.field}): {self.message}"


@dataclass
class ImportPreview:
    """The result of validating a CSV before committing anything."""

    total_rows: int = 0
    valid_rows: list[dict] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid_rows)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass
class ImportResult:
    """The outcome of committing an import."""

    imported: int = 0
    skipped: int = 0
    errors: list[ImportRowError] = field(default_factory=list)


@dataclass
class ProductStock:
    """A product paired with its live stock numbers (for tables/detail views)."""

    product: Product
    stock_level: float
    usable_stock: float
    status: str
    batch_count: int = 0
    nearest_expiry: str | None = None


@dataclass
class DashboardStats:
    """Real, database-derived dashboard metrics (never fabricated)."""

    total_products: int = 0
    total_stock_value: Decimal = Decimal("0")
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    near_expiry_count: int = 0
    expired_batch_count: int = 0
    sales_today_total: Decimal = Decimal("0")
    low_stock_items: list[ProductStock] = field(default_factory=list)
    expiring_batches: list[tuple[Product, InventoryBatch]] = field(default_factory=list)
    recent_movements: list[tuple[Product, StockMovement]] = field(default_factory=list)
