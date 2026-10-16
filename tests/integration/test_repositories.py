"""Integration tests for the SQLite repositories (real DB, no mocks)."""

from __future__ import annotations

from decimal import Decimal

from domain.entities import InventoryBatch, Product, ProductSupplier, Sale, SaleItem, StockMovement, Supplier
from domain.enums import MovementType


class TestProductRepository:
    def test_create_and_fetch(self, ctx):
        created = ctx.products.create(Product(sku="SKU-1", name="Rice 1kg", cost_price=Decimal("40"), selling_price=Decimal("55")))
        assert created.id is not None
        fetched = ctx.products.get_by_sku("SKU-1")
        assert fetched.name == "Rice 1kg"
        assert fetched.selling_price == Decimal("55.00")

    def test_search_and_category_filter(self, ctx):
        ctx.products.create(Product(sku="A", name="Apple", category="Fruit"))
        ctx.products.create(Product(sku="B", name="Banana", category="Fruit"))
        ctx.products.create(Product(sku="C", name="Carrot", category="Veg"))
        assert len(ctx.products.list_all(category="Fruit")) == 2
        assert [p.sku for p in ctx.products.list_all(search_query="ban")] == ["B"]

    def test_archive_hides_from_active_list(self, ctx):
        p = ctx.products.create(Product(sku="X", name="X"))
        assert ctx.products.archive(p.id) is True
        assert ctx.products.get_by_id(p.id).active is False
        assert all(row.id != p.id for row in ctx.products.list_all(active_only=True))


class TestSupplierRepository:
    def test_link_and_preferred_supplier(self, ctx):
        p = ctx.products.create(Product(sku="P", name="Product"))
        s1 = ctx.suppliers.create(Supplier(name="Supplier One"))
        s2 = ctx.suppliers.create(Supplier(name="Supplier Two"))
        ctx.suppliers.link_product_supplier(ProductSupplier(product_id=p.id, supplier_id=s1.id, lead_time_days=5))
        ctx.suppliers.link_product_supplier(ProductSupplier(product_id=p.id, supplier_id=s2.id, lead_time_days=1, is_preferred=True))

        links = ctx.suppliers.get_product_suppliers(p.id)
        assert len(links) == 2
        preferred = ctx.suppliers.get_preferred_supplier(p.id)
        assert preferred[1].name == "Supplier Two"

    def test_relink_updates_in_place(self, ctx):
        p = ctx.products.create(Product(sku="P", name="Product"))
        s = ctx.suppliers.create(Supplier(name="S"))
        ctx.suppliers.link_product_supplier(ProductSupplier(product_id=p.id, supplier_id=s.id, lead_time_days=3))
        ctx.suppliers.link_product_supplier(ProductSupplier(product_id=p.id, supplier_id=s.id, lead_time_days=9))
        links = ctx.suppliers.get_product_suppliers(p.id)
        assert len(links) == 1 and links[0][0].lead_time_days == 9


class TestInventoryRepository:
    def test_stock_level_sums_ledger(self, ctx):
        p = ctx.products.create(Product(sku="P", name="Product"))
        ctx.inventory_repo.create_batch(InventoryBatch(product_id=p.id, quantity_received=10, quantity_remaining=10))
        ctx.inventory_repo.add_movement(StockMovement(product_id=p.id, movement_type=MovementType.OPENING_STOCK, quantity_delta=10, balance_after=10))
        ctx.inventory_repo.add_movement(StockMovement(product_id=p.id, movement_type=MovementType.SALE, quantity_delta=-4, balance_after=6))
        assert ctx.inventory_repo.stock_level(p.id) == 6

    def test_movement_exists_ignores_type_when_not_given(self, ctx):
        p = ctx.products.create(Product(sku="P", name="Product"))
        ctx.inventory_repo.add_movement(StockMovement(product_id=p.id, movement_type=MovementType.PURCHASE_RECEIPT, quantity_delta=1, balance_after=1, source_type="po", source_id="1"))
        assert ctx.inventory_repo.movement_exists("po", "1") is True
        assert ctx.inventory_repo.movement_exists("po", "2") is False


class TestSalesRepository:
    def test_create_sale_with_items_and_daily_demand(self, ctx):
        p = ctx.products.create(Product(sku="P", name="Product"))
        sale = ctx.sales_repo.create_sale(Sale(items=[SaleItem(product_id=p.id, quantity=2, unit_price=Decimal("10"), line_total=Decimal("20"))], total_amount=Decimal("20")))
        assert sale.id is not None
        items = ctx.sales_repo.get_items(sale.id)
        assert len(items) == 1 and items[0].line_total == Decimal("20.00")
        assert ctx.sales_repo.total_amount_for_date(sale.sold_at[:10]) == Decimal("20.00")

    def test_external_ref_unique_index(self, ctx):
        p = ctx.products.create(Product(sku="P", name="Product"))
        ctx.sales_repo.create_sale(Sale(source="csv_import", external_ref="INV-1", items=[SaleItem(product_id=p.id, quantity=1)]))
        assert ctx.sales_repo.find_by_external_ref("csv_import", "INV-1") is not None
