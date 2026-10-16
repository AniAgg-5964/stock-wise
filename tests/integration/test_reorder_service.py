"""Integration tests for the reorder service (forecast + constraints + persistence)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product, ProductSupplier, Supplier


def _product(ctx, sku="RO-1", safety=5):
    return ctx.product_service.create_product(
        Product(sku=sku, name=f"Reorder {sku}", category="Test", unit="pcs",
                cost_price=Decimal("40"), selling_price=Decimal("50"),
                reorder_point=10, safety_stock=safety)
    )


def _supplier_with_link(ctx, product_id, *, lead=3, moq=1, pack=1, cost=Decimal("40")):
    supplier = ctx.supplier_service.create_supplier(Supplier(name=f"Sup {product_id}"))
    ctx.supplier_service.link_product_supplier(ProductSupplier(
        product_id=product_id, supplier_id=supplier.id, lead_time_days=lead,
        minimum_order_qty=moq, pack_size=pack, unit_cost=cost, is_preferred=True,
    ))
    return supplier


def _seed_demand(ctx, product_id, days=40, daily=10.0):
    with ctx.db.get_connection() as conn:
        start = date.today() - timedelta(days=days)
        for i in range(days):
            day = start + timedelta(days=i)
            conn.execute(
                "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?,?,?)",
                (day.isoformat(), product_id, daily),
            )


class TestReorderService:
    def test_recommends_when_stock_is_low(self, ctx):
        product = _product(ctx)
        _supplier_with_link(ctx, product.id)
        _seed_demand(ctx, product.id)
        ctx.inventory_service.receive_stock(product.id, 5, unit_cost=Decimal("40"))

        reco = ctx.reorder_service.recommend_for_product(product.id)

        assert reco.product_id == product.id
        assert reco.protection_period_days == 5
        assert reco.suggested_qty > 0
        assert reco.estimated_cost == (reco.unit_cost * reco.suggested_qty).quantize(Decimal("0.01"))

    def test_no_order_when_well_stocked(self, ctx):
        product = _product(ctx)
        _supplier_with_link(ctx, product.id)
        _seed_demand(ctx, product.id, daily=5.0)
        ctx.inventory_service.receive_stock(product.id, 1000, unit_cost=Decimal("40"))

        reco = ctx.reorder_service.recommend_for_product(product.id)

        assert reco.needs_order is False

    def test_confirmed_incoming_reduces_order(self, ctx):
        product = _product(ctx)
        _supplier_with_link(ctx, product.id)
        _seed_demand(ctx, product.id)
        ctx.inventory_service.receive_stock(product.id, 5, unit_cost=Decimal("40"))

        before = ctx.reorder_service.recommend_for_product(product.id)
        ctx.purchase_orders.create(
            supplier_id=None, items=[(product.id, 50, 40.0)], status="confirmed"
        )
        after = ctx.reorder_service.recommend_for_product(product.id)

        assert ctx.purchase_orders.confirmed_incoming_qty(product.id) == 50
        assert after.confirmed_incoming == 50
        assert after.raw_qty == max(0.0, before.raw_qty - 50)

    def test_draft_orders_do_not_count_as_incoming(self, ctx):
        product = _product(ctx)
        ctx.purchase_orders.create(supplier_id=None, items=[(product.id, 20, 40.0)], status="draft")
        assert ctx.purchase_orders.confirmed_incoming_qty(product.id) == 0

    def test_budget_caps_the_order(self, ctx):
        product = _product(ctx)
        _supplier_with_link(ctx, product.id, cost=Decimal("70"))
        _seed_demand(ctx, product.id, daily=10.0)
        ctx.inventory_service.receive_stock(product.id, 1, unit_cost=Decimal("70"))

        reco = ctx.reorder_service.recommend_for_product(product.id, budget=Decimal("700"))

        assert reco.budget is not None
        assert reco.budget_capped_qty is not None
        assert reco.suggested_qty == 10  # floor(700 / 70)

    def test_recommend_all_is_urgency_sorted(self, ctx):
        low = _product(ctx, sku="RO-LOW")
        _supplier_with_link(ctx, low.id)
        _seed_demand(ctx, low.id)
        ctx.inventory_service.receive_stock(low.id, 3, unit_cost=Decimal("40"))

        recos = ctx.reorder_service.recommend_all()

        assert recos and recos[0].product_id == low.id
        assert all(r.needs_order for r in recos)

    def test_persistence_and_status(self, ctx):
        product = _product(ctx)
        _supplier_with_link(ctx, product.id)
        _seed_demand(ctx, product.id)
        ctx.inventory_service.receive_stock(product.id, 2, unit_cost=Decimal("40"))

        reco = ctx.reorder_service.recommend_for_product(product.id)
        reco_id = ctx.reorder_service.save(reco)
        ctx.reorder_service.update_status(reco_id, "accepted", reviewed_qty=reco.suggested_qty)

        saved = ctx.reorder_service.list_saved()
        assert saved[0]["status"] == "accepted"
        assert saved[0]["rationale"]["suggested_qty"] == reco.suggested_qty

    def test_record_order_creates_confirmed_po(self, ctx):
        product = _product(ctx)
        supplier = _supplier_with_link(ctx, product.id)
        _seed_demand(ctx, product.id)
        ctx.inventory_service.receive_stock(product.id, 2, unit_cost=Decimal("40"))

        reco = ctx.reorder_service.recommend_for_product(product.id)
        po_id = ctx.reorder_service.create_purchase_order(reco)

        po = ctx.purchase_orders.get(po_id)
        assert po["status"] == "confirmed"
        assert po["items"][0]["product_id"] == product.id
        assert ctx.purchase_orders.confirmed_incoming_qty(product.id) == reco.suggested_qty

    def test_reorder_view_constructs(self, wired_app_context):
        from ui.views.reorder_view import build_reorder_view

        control = build_reorder_view(page=None, navigate=lambda r: None)
        assert control is not None
