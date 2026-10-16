"""Acceptance tests \u2014 the end-to-end decision-support loop (PRD 13.2, stages 3\u20139).

These drive the full stack the way the UI does: demand history \u2192 forecast \u2192
reorder recommendation \u2192 confirmed incoming \u2192 alerts and reports \u2014 and encode
that recommendations stay advisory and explainable.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product, ProductSupplier, Sale, SaleItem, Supplier


def _daily(quantity: float) -> float:
    return quantity


def _product(ctx, sku="DST-1", *, reorder_point=10, safety=5):
    return ctx.product_service.create_product(
        Product(sku=sku, name=f"Decision {sku}", category="Grocery", unit="pcs",
                cost_price=Decimal("40"), selling_price=Decimal("50"),
                reorder_point=reorder_point, safety_stock=safety, expiry_tracking=True)
    )


def _seed_demand_history(ctx, product_id, *, days=45, daily=8.0):
    with ctx.db.get_connection() as conn:
        start = date.today() - timedelta(days=days)
        for i in range(days):
            conn.execute(
                "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?,?,?)",
                ((start + timedelta(days=i)).isoformat(), product_id, daily),
            )


def _link_supplier(ctx, product_id, *, lead=3, moq=1, pack=1, cost=Decimal("40")):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="Daily Distributors"))
    ctx.supplier_service.link_product_supplier(ProductSupplier(
        product_id=product_id, supplier_id=supplier.id, lead_time_days=lead,
        minimum_order_qty=moq, pack_size=pack, unit_cost=cost, is_preferred=True,
    ))
    return supplier


class TestDecisionSupportLoop:
    def test_low_stock_to_explainable_order(self, ctx):
        product = _product(ctx)
        _link_supplier(ctx, product.id, lead=3)
        _seed_demand_history(ctx, product.id, daily=8.0)
        ctx.inventory_service.receive_stock(product.id, 6, unit_cost=Decimal("40"))

        # 1. Forecast is generated and is honest about its method.
        forecast = ctx.forecast_service.generate(product.id, horizon=7)
        assert forecast is not None and forecast.points
        assert forecast.average_daily_demand > 0

        # 2. A recommendation is produced with a full explanation.
        reco = ctx.reorder_service.recommend_for_product(product.id)
        assert reco.needs_order is True
        rationale = reco.rationale()
        assert rationale["protection_period_days"] == 5   # L=3, R=2
        assert rationale["target_position"] > 0
        assert rationale["suggested_qty"] > 0
        assert reco.suggested_qty == rationale["suggested_qty"]

        # 3. Recording the owner's order makes it confirmed incoming stock.
        po_id = ctx.reorder_service.create_purchase_order(reco)
        assert ctx.purchase_orders.get(po_id)["status"] == "confirmed"
        assert ctx.purchase_orders.confirmed_incoming_qty(product.id) == reco.suggested_qty

        # 4. Re-running the recommendation accounts for the incoming order.
        after = ctx.reorder_service.recommend_for_product(product.id)
        assert after.raw_qty < reco.raw_qty or after.suggested_qty <= reco.suggested_qty

    def test_recommendation_is_advisory_only(self, ctx):
        product = _product(ctx, "DST-2")
        _link_supplier(ctx, product.id)
        _seed_demand_history(ctx, product.id)
        ctx.inventory_service.receive_stock(product.id, 1, unit_cost=Decimal("40"))

        before = ctx.purchase_orders.list_open()
        ctx.reorder_service.recommend_for_product(product.id)
        # Computing a suggestion must not create any order.
        assert ctx.purchase_orders.list_open() == before

    def test_expiry_risk_is_flagged_not_hidden(self, ctx):
        product = _product(ctx, "DST-3")
        _link_supplier(ctx, product.id)
        _seed_demand_history(ctx, product.id, daily=1.0)
        soon = (date.today() + timedelta(days=2)).isoformat()
        ctx.inventory_service.receive_stock(product.id, 60, unit_cost=Decimal("40"), expiry_date=soon)

        reco = ctx.reorder_service.recommend_for_product(product.id)

        assert reco.expiry_review_required is True
        assert any("expire" in note.lower() for note in reco.notes)

    def test_alerts_and_reports_reflect_state(self, ctx, tmp_path):
        product = _product(ctx, "DST-4")
        empty = _product(ctx, "DST-4B")  # no stock at all
        _link_supplier(ctx, product.id)
        _seed_demand_history(ctx, product.id)
        ctx.inventory_service.receive_stock(product.id, 100, unit_cost=Decimal("40"))
        ctx.sales_service.record_sale(Sale(items=[SaleItem(product_id=product.id, quantity=5)]))

        alerts = ctx.alert_service.build()
        kinds = {a.kind for a in alerts}
        assert "out_of_stock" in kinds
        assert any(a.product_id == empty.id for a in alerts if a.kind == "out_of_stock")

        valuation = ctx.report_service.stock_valuation()
        row = next(r for r in valuation["rows"] if r["product_id"] == product.id)
        assert row["qty"] == 95  # 100 received - 5 sold
        assert valuation["total_value"] > 0

        target = ctx.report_service.export_csv(
            tmp_path / "acceptance_valuation.csv",
            ["product_id", "name", "qty", "value"],
            valuation["rows"],
        )
        assert target.exists() and product.name in target.read_text(encoding="utf-8")


class TestReorderFixture:
    """The worked numeric example from the implementation plan (acceptance #5)."""

    def test_budget_capped_order_matches_hand_calculation(self):
        from domain.reorder import ReorderContext, compute

        reco = compute(ReorderContext(
            product_id=1, product_name="Fixture", unit="pcs",
            forecast=[8, 10, 9, 12, 11], avg_daily_demand=10.0, usable_on_hand=36.0,
            lead_time_days=3, review_period_days=2, safety_stock=6.0,
            unit_cost=Decimal("70"), budget=Decimal("1000"),
        ))

        assert reco.target_position == 56
        assert reco.inventory_position == 36
        assert reco.raw_qty == 20
        assert reco.suggested_qty == 14
        assert reco.shortfall == 6
