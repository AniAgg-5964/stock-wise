"""Integration tests for prediction intervals, best-baseline fallback and the
statistical safety-stock policy (the "honesty gaps" closed after the model build).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product, ProductSupplier, Supplier


def _product(ctx, sku="GAP-1", safety=0):
    return ctx.product_service.create_product(
        Product(sku=sku, name=f"Gap {sku}", category="Test", unit="pcs",
                cost_price=Decimal("40"), selling_price=Decimal("50"),
                reorder_point=10, safety_stock=safety)
    )


def _link_supplier(ctx, product_id, *, lead=3, cost=Decimal("40")):
    supplier = ctx.supplier_service.create_supplier(Supplier(name=f"Sup {product_id}"))
    ctx.supplier_service.link_product_supplier(ProductSupplier(
        product_id=product_id, supplier_id=supplier.id, lead_time_days=lead,
        minimum_order_qty=1, pack_size=1, unit_cost=cost, is_preferred=True,
    ))
    return supplier


def _seed(ctx, product_id, days, fn):
    with ctx.db.get_connection() as conn:
        start = date.today() - timedelta(days=days)
        for i in range(days):
            day = start + timedelta(days=i)
            conn.execute(
                "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?,?,?)",
                (day.isoformat(), product_id, float(fn(i, day))),
            )


class TestPredictionIntervals:
    def test_generate_persists_widening_bounds(self, ctx):
        product = _product(ctx, sku="GAP-IV")
        # Noisy demand so variability (and therefore an interval) actually exists.
        _seed(ctx, product.id, 42, lambda i, day: 10 + day.weekday() + (0 if i % 3 else 5))

        result = ctx.forecast_service.generate(product.id, horizon=7)

        assert result.residual_std > 0
        assert result.interval_level == 0.90
        assert all(p.lower_bound is not None and p.upper_bound is not None for p in result.points)
        widths = [p.upper_bound - p.lower_bound for p in result.points]
        assert widths[0] < widths[-1]  # uncertainty grows with the horizon
        assert all(p.lower_bound >= 0 for p in result.points)

        stored = ctx.forecast_repo.get_forecasts(product.id)
        assert all(row["lower_bound"] is not None for row in stored)

        latest = ctx.forecast_service.latest(product.id)
        assert latest.interval_level == 0.90

    def test_interval_level_follows_the_setting(self, ctx):
        product = _product(ctx, sku="GAP-IV2")
        _seed(ctx, product.id, 42, lambda i, day: 10 + day.weekday() + (0 if i % 3 else 5))
        ctx.settings.set("service_level", "0.95")

        result = ctx.forecast_service.generate(product.id, horizon=7)

        assert result.interval_level == 0.95


class TestBestBaselineFallback:
    def test_trending_demand_picks_moving_average(self, ctx):
        product = _product(ctx, sku="GAP-BEST")
        _seed(ctx, product.id, 42, lambda i, day: 10 + i)  # steady upward trend

        result = ctx.forecast_service.generate(product.id, horizon=7)

        assert result.is_baseline is True
        assert result.method == "moving_average"
        assert "most accurate baseline" in result.note

    def test_pinned_baseline_setting_is_respected(self, ctx):
        product = _product(ctx, sku="GAP-PIN")
        _seed(ctx, product.id, 42, lambda i, day: 10 + i)
        ctx.settings.set("forecast_baseline_method", "mean")

        result = ctx.forecast_service.generate(product.id, horizon=7)

        assert result.method == "mean"


class TestStatisticalSafetyStock:
    def test_statistical_policy_is_reported_and_applied(self, ctx):
        product = _product(ctx, sku="GAP-SS")
        _link_supplier(ctx, product.id)
        _seed(ctx, product.id, 45, lambda i, day: 10 + day.weekday() + (0 if i % 4 else 4))
        ctx.inventory_service.receive_stock(product.id, 2, unit_cost=Decimal("40"))
        ctx.settings.set("safety_policy", "statistical")
        ctx.settings.set("service_level", "0.95")

        reco = ctx.reorder_service.recommend_for_product(product.id)

        assert reco.safety_stock > 0
        assert any("Statistical safety stock" in n for n in reco.notes)

    def test_statistical_without_variability_degrades_to_heuristic(self, ctx):
        product = _product(ctx, sku="GAP-SS2")
        _link_supplier(ctx, product.id)
        _seed(ctx, product.id, 5, lambda i, day: 10.0)  # too little history to estimate sigma
        ctx.inventory_service.receive_stock(product.id, 20, unit_cost=Decimal("40"))
        ctx.settings.set("safety_policy", "statistical")

        # Force a stored forecast with no residual estimate by pinning the mean.
        reco = ctx.reorder_service.recommend_for_product(product.id)

        assert any("heuristic instead" in n for n in reco.notes)

    def test_heuristic_policy_has_no_policy_note(self, ctx):
        product = _product(ctx, sku="GAP-SS3")
        _link_supplier(ctx, product.id)
        _seed(ctx, product.id, 40, lambda i, day: 10.0)
        ctx.inventory_service.receive_stock(product.id, 5, unit_cost=Decimal("40"))

        reco = ctx.reorder_service.recommend_for_product(product.id)

        assert not any("safety stock" in n for n in reco.notes)
