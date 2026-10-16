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
class ForecastPoint:
    """One forecast day for a product."""

    target_date: str
    predicted_qty: float
    lower_bound: float | None = None
    upper_bound: float | None = None


@dataclass
class ForecastMetrics:
    """Accuracy metrics for one forecasting method."""

    method: str
    label: str
    mae: float = 0.0
    rmse: float = 0.0
    wape: float | None = None
    bias: float = 0.0
    n: int = 0


@dataclass
class ForecastResult:
    """A generated forecast plus the context the UI needs to explain it."""

    product_id: int
    product_name: str
    horizon: int
    method: str
    method_label: str
    generated_at: str | None = None
    is_baseline: bool = True
    fallback_used: bool = False
    insufficient_data: bool = False
    average_daily_demand: float = 0.0
    observed_days: int = 0
    residual_std: float = 0.0
    note: str = ""
    points: list[ForecastPoint] = field(default_factory=list)

    @property
    def total_qty(self) -> float:
        return sum(p.predicted_qty for p in self.points)


@dataclass
class Alert:
    """A single actionable alert shown on the dashboard / expiry screen."""

    kind: str            # out_of_stock | low_stock | near_expiry | expired | expiry_risk | demand_spike
    severity: str        # critical | warning | info
    title: str
    message: str
    route: str = "/"
    product_id: int | None = None


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
