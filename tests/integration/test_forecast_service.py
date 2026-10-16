"""Integration tests for ``ForecastService`` (demand pipeline + persistence)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product


def _make_product(ctx, sku="FOR-1", name="Forecast Item"):
    return ctx.product_service.create_product(
        Product(sku=sku, name=name, category="Test", unit="pcs",
                cost_price=Decimal("10"), selling_price=Decimal("15"))
    )


def _seed_demand(ctx, product_id, days, pattern=None):
    today = date.today()
    with ctx.db.get_connection() as conn:
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            if pattern is not None:
                qty = pattern(day)
            else:
                qty = 10 + (day.weekday() * 2)
            conn.execute(
                "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?, ?, ?)",
                (day.isoformat(), product_id, float(qty)),
            )


class TestForecastService:
    def test_generates_and_persists_forecast(self, ctx):
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 42)

        result = ctx.forecast_service.generate(product.id, horizon=7)

        assert result.horizon == 7
        assert len(result.points) == 7
        assert result.insufficient_data is False
        assert result.method == "seasonal_naive"
        assert result.observed_days >= 42
        # persisted
        stored = ctx.forecast_repo.get_forecasts(product.id)
        assert len(stored) == 7
        # forecast starts tomorrow
        expected_first = (date.today() + timedelta(days=1)).isoformat()
        assert stored[0]["target_date"] == expected_first

    def test_insufficient_history_uses_average(self, ctx):
        product = _make_product(ctx, sku="FOR-2")
        _seed_demand(ctx, product.id, 3)

        result = ctx.forecast_service.generate(product.id, horizon=7)

        assert result.insufficient_data is True
        assert result.method == "mean"
        assert result.note

    def test_backtest_returns_baselines(self, ctx):
        product = _make_product(ctx, sku="FOR-3")
        _seed_demand(ctx, product.id, 42)

        metrics = ctx.forecast_service.backtest(product.id, horizon=7)

        methods = {m.method for m in metrics}
        assert {"seasonal_naive", "moving_average", "mean"} <= methods
        assert all(m.n == 7 for m in metrics)

    def test_forecast_demand_sums_protection_period(self, ctx):
        product = _make_product(ctx, sku="FOR-4")
        _seed_demand(ctx, product.id, 42)

        total, result = ctx.forecast_service.forecast_demand(product.id, days=5)

        assert len(result.points) >= 5
        assert abs(total - sum(p.predicted_qty for p in result.points[:5])) < 1e-6

    def test_latest_round_trips(self, ctx):
        product = _make_product(ctx, sku="FOR-5")
        _seed_demand(ctx, product.id, 30)
        ctx.forecast_service.generate(product.id, horizon=7)

        latest = ctx.forecast_service.latest(product.id)

        assert latest is not None
        assert latest.horizon == 7
        assert len(latest.points) == 7

    def test_forecasting_view_constructs(self, wired_app_context):
        from ui.views.forecasting_view import build_forecasting_view

        control = build_forecasting_view(page=None, navigate=lambda r: None)
        assert control is not None
