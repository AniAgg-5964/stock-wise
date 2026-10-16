"""Acceptance tests — the P0 core workflows from the product spec (§13.2).

These exercise the full stack (services → repositories → SQLite) and encode the
non-negotiable rules: atomic sales, no oversell by default, idempotent receipts,
FEFO + expiry exclusion, and CRUD.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from domain.entities import Product, ProductSupplier, Sale, SaleItem, Supplier
from domain.enums import MovementType
from domain.exceptions import (
    DuplicateImportError,
    InsufficientStockError,
    ValidationError,
)


def _make_product(ctx, sku="MILK", name="Milk 500ml", **kwargs):
    defaults = dict(
        cost_price=Decimal("25"), selling_price=Decimal("28"),
        reorder_point=10, safety_stock=5,
    )
    defaults.update(kwargs)
    return ctx.product_service.create_product(Product(sku=sku, name=name, **defaults))


# --------------------------------------------------------------------- Test 1
def test_stock_20_sell_3_leaves_17_and_records_ledger(ctx):
    product = _make_product(ctx)
    ctx.inventory_service.receive_stock(
        product.id, 20, unit_cost=Decimal("25"),
        movement_type=MovementType.OPENING_STOCK, source_type="opening", source_id="open-1",
    )
    assert ctx.inventory_service.stock_level(product.id) == 20
    assert ctx.inventory_service.usable_stock(product.id) == 20

    sale = ctx.sales_service.record_sale(
        Sale(items=[SaleItem(product_id=product.id, quantity=3)])
    )

    assert ctx.inventory_service.stock_level(product.id) == 17
    assert ctx.inventory_service.usable_stock(product.id) == 17
    assert sale.id is not None
    assert sale.total_amount == Decimal("84.00")

    movements = ctx.inventory_service.get_movements(product.id)
    sale_moves = [m for m in movements if m.movement_type == "sale"]
    assert len(sale_moves) == 1
    assert sale_moves[0].quantity_delta == -3
    assert sale_moves[0].balance_after == 17


def test_failed_sale_rolls_back_completely(ctx):
    """A sale is atomic: one bad line means no sale and no stock movement."""
    good = _make_product(ctx, sku="A", name="In stock")
    empty = _make_product(ctx, sku="B", name="Empty")
    ctx.inventory_service.receive_stock(good.id, 20, movement_type=MovementType.OPENING_STOCK)

    with pytest.raises(InsufficientStockError):
        ctx.sales_service.record_sale(
            Sale(items=[
                SaleItem(product_id=good.id, quantity=5),
                SaleItem(product_id=empty.id, quantity=1),  # fails mid-transaction
            ])
        )

    assert ctx.sales_repo.list_recent() == []
    assert ctx.inventory_service.stock_level(good.id) == 20
    assert ctx.inventory_service.usable_stock(empty.id) == 0


# --------------------------------------------------------------------- Test 2
def test_oversell_blocked_then_allowed_with_override(ctx):
    product = _make_product(ctx, sku="SODA", name="Soda", cost_price=Decimal("20"), selling_price=Decimal("30"))
    ctx.inventory_service.receive_stock(product.id, 5, movement_type=MovementType.OPENING_STOCK)

    with pytest.raises(InsufficientStockError):
        ctx.sales_service.record_sale(Sale(items=[SaleItem(product_id=product.id, quantity=10)]))
    assert ctx.inventory_service.stock_level(product.id) == 5
    assert ctx.sales_repo.list_recent() == []

    sale = ctx.sales_service.record_sale(
        Sale(items=[SaleItem(product_id=product.id, quantity=10)]), allow_override=True
    )
    assert sale.id is not None
    assert ctx.inventory_service.stock_level(product.id) == -5

    events = [e["event_type"] for e in ctx.audit.list_events(entity_type="sale")]
    assert "sale_override" in events


# --------------------------------------------------------------------- Test 3
def test_duplicate_receipt_is_rejected(ctx):
    product = _make_product(ctx)
    ctx.inventory_service.receive_stock(
        product.id, 10, source_type="purchase_order", source_id="PO-100",
        movement_type=MovementType.PURCHASE_RECEIPT,
    )
    with pytest.raises(DuplicateImportError):
        ctx.inventory_service.receive_stock(
            product.id, 10, source_type="purchase_order", source_id="PO-100",
            movement_type=MovementType.PURCHASE_RECEIPT,
        )
    assert ctx.inventory_service.stock_level(product.id) == 10


def test_duplicate_sale_external_ref_is_rejected(ctx):
    product = _make_product(ctx)
    ctx.inventory_service.receive_stock(product.id, 10, movement_type=MovementType.OPENING_STOCK)
    payload = dict(source="csv_import", external_ref="INV-7", items=[SaleItem(product_id=product.id, quantity=1)])
    ctx.sales_service.record_sale(Sale(**payload))
    with pytest.raises(DuplicateImportError):
        ctx.sales_service.record_sale(Sale(**{**payload, "items": [SaleItem(product_id=product.id, quantity=1)]}))
    assert ctx.inventory_service.stock_level(product.id) == 9


# --------------------------------------------------------------------- Test 4
def test_expired_stock_excluded_and_fefo_consumption(ctx):
    product = _make_product(ctx, sku="YOG", name="Yoghurt", expiry_tracking=True, reorder_point=3)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    soon = (date.today() + timedelta(days=5)).isoformat()
    later = (date.today() + timedelta(days=30)).isoformat()

    ctx.inventory_service.receive_stock(product.id, 10, expiry_date=yesterday, batch_code="A")
    ctx.inventory_service.receive_stock(product.id, 8, expiry_date=soon, batch_code="B")
    ctx.inventory_service.receive_stock(product.id, 5, expiry_date=later, batch_code="C")

    assert ctx.inventory_service.stock_level(product.id) == 23   # physical
    assert ctx.inventory_service.usable_stock(product.id) == 13  # expired excluded

    ctx.sales_service.record_sale(Sale(items=[SaleItem(product_id=product.id, quantity=6)]))

    batches = {b.batch_code: b for b in ctx.inventory_service.get_batches(product.id, include_depleted=True)}
    assert batches["A"].quantity_remaining == 10  # expired batch never consumed
    assert batches["B"].quantity_remaining == 2   # FEFO took the 6 from B
    assert batches["C"].quantity_remaining == 5
    assert ctx.inventory_service.usable_stock(product.id) == 7

    with pytest.raises(InsufficientStockError):
        ctx.sales_service.record_sale(Sale(items=[SaleItem(product_id=product.id, quantity=8)]))


# --------------------------------------------------------------------- Test 5
def test_product_and_supplier_crud_with_mapping(ctx):
    product = _make_product(ctx, sku="ATTA", name="Atta 5kg")
    ctx.product_service.update_product(
        Product(id=product.id, sku="ATTA", name="Atta 5kg Premium",
                cost_price=Decimal("210"), selling_price=Decimal("260"))
    )
    assert ctx.product_service.get_product(product.id).name == "Atta 5kg Premium"

    supplier = ctx.supplier_service.create_supplier(Supplier(name="Sharma Distributors", phone="9999999999"))
    ctx.supplier_service.link_product_supplier(
        ProductSupplier(product_id=product.id, supplier_id=supplier.id, lead_time_days=2,
                        minimum_order_qty=5, is_preferred=True)
    )
    link, linked_supplier = ctx.supplier_service.get_preferred_supplier(product.id)
    assert linked_supplier.name == "Sharma Distributors"
    assert link.lead_time_days == 2

    ctx.product_service.archive_product(product.id)
    assert ctx.product_service.get_product(product.id).active is False


def test_duplicate_sku_rejected(ctx):
    _make_product(ctx, sku="DUP", name="First")
    with pytest.raises(ValidationError):
        _make_product(ctx, sku="DUP", name="Second")
