"""StockWise — domain entities.

Plain dataclasses. Money fields use ``Decimal``; repositories convert at the
SQLite boundary. ``id`` is ``None`` until persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.enums import MovementType


@dataclass
class Product:
    sku: str
    name: str
    id: int | None = None
    category: str = "General"
    unit: str = "pcs"
    brand: str | None = None
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    reorder_point: int = 10
    safety_stock: int = 5
    expiry_tracking: bool = False
    active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class Supplier:
    name: str
    id: int | None = None
    contact: str | None = None
    email: str | None = None
    phone: str | None = None
    website_url: str | None = None
    address: str | None = None
    notes: str | None = None
    active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class ProductSupplier:
    product_id: int
    supplier_id: int
    id: int | None = None
    supplier_sku: str | None = None
    lead_time_days: int = 3
    minimum_order_qty: int = 1
    pack_size: int = 1
    unit_cost: Decimal | None = None
    is_preferred: bool = False
    last_verified_at: str | None = None


@dataclass
class InventoryBatch:
    product_id: int
    quantity_received: float
    quantity_remaining: float
    id: int | None = None
    batch_code: str | None = None
    received_at: str | None = None
    expiry_date: str | None = None
    unit_cost: Decimal | None = None


@dataclass
class StockMovement:
    product_id: int
    movement_type: MovementType | str
    quantity_delta: float
    balance_after: float
    id: int | None = None
    batch_id: int | None = None
    occurred_at: str | None = None
    reason: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    created_by: str | None = None


@dataclass
class SaleItem:
    product_id: int
    quantity: float
    unit_price: Decimal = Decimal("0")
    id: int | None = None
    sale_id: int | None = None
    unit_cost_snapshot: Decimal | None = None
    line_total: Decimal = Decimal("0")
    product_name: str | None = None  # denormalised for display only


@dataclass
class Sale:
    items: list[SaleItem] = field(default_factory=list)
    id: int | None = None
    sold_at: str | None = None
    source: str = "manual"
    external_ref: str | None = None
    notes: str | None = None
    total_amount: Decimal = Decimal("0")
    created_at: str | None = None


@dataclass
class DailyDemand:
    product_id: int
    demand_date: str
    quantity_sold: float = 0.0
    observed_flag: bool = True
    stockout_flag: bool = False
    id: int | None = None


@dataclass
class AuditEvent:
    event_type: str
    id: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    occurred_at: str | None = None
    details: dict = field(default_factory=dict)
    created_by: str | None = None


@dataclass
class ExternalSource:
    """A web page consulted during supplier research (TinyFish).

    ``parse_status`` records how far the page got: ``pending`` when discovered,
    ``ok`` when extracted, or a rejection reason (``login_wall``, ``too_short``…)
    when the page was unusable.
    """

    provider: str
    id: int | None = None
    url: str | None = None
    retrieved_at: str | None = None
    query: str | None = None
    status_code: int | None = None
    parse_status: str = "pending"
    content_hash: str | None = None


@dataclass
class SupplierObservation:
    """A single fact found on the web about a product or supplier.

    Observations are *candidates*: nothing reaches ``product_suppliers`` until the
    user verifies and applies them. ``field_value`` stays text so a scraped page
    can never inject a non-numeric value into a money column.
    """

    field_name: str
    field_value: str
    id: int | None = None
    source_id: int | None = None
    supplier_id: int | None = None
    product_id: int | None = None
    currency: str | None = None
    confidence: float = 0.0
    verified_by_user: bool = False
    observed_at: str | None = None
