"""Integration tests for the reporting service (real data, real aggregates)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product, Sale, SaleItem


def _product(ctx, sku="RP-1", *, cost="10", price="20"):
    return ctx.product_service.create_product(
        Product(sku=sku, name=f"Report {sku}", category="Test", unit="pcs",
                cost_price=Decimal(cost), selling_price=Decimal(price),
                reorder_point=5, safety_stock=3)
    )


def _seed_demand(ctx, product_id, days=40, daily=4.0):
    with ctx.db.get_connection() as conn:
        start = date.today() - timedelta(days=days)
        for i in range(days):
            conn.execute(
                "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?,?,?)",
                ((start + timedelta(days=i)).isoformat(), product_id, daily),
            )


class TestSalesReports:
    def test_sales_summary_and_trend(self, ctx):
        product = _product(ctx)
        ctx.inventory_service.receive_stock(product.id, 100, unit_cost=Decimal("10"))
        ctx.sales_service.record_sale(Sale(items=[SaleItem(product_id=product.id, quantity=10)]))

        summary = ctx.report_service.sales_summary(30)
        assert summary["orders"] == 1
        assert summary["units"] == 10
        assert summary["revenue"] == Decimal("200.00")
        assert summary["margin"] == Decimal("100.00")

        by_day = ctx.report_service.sales_by_day(30)
        assert len(by_day) == 1
        assert by_day[0]["units"] == 10

        top = ctx.report_service.top_products(30)
        assert top[0]["name"] == product.name
        assert top[0]["qty"] == 10

    def test_empty_sales_period_is_zeroed(self, ctx):
        summary = ctx.report_service.sales_summary(7)
        assert summary["orders"] == 0
        assert summary["revenue"] == Decimal("0.00")
        assert ctx.report_service.sales_by_day(7) == []


class TestStockAndWasteReports:
    def test_stock_valuation_totals(self, ctx):
        product = _product(ctx)
        ctx.inventory_service.receive_stock(product.id, 90, unit_cost=Decimal("10"))

        valuation = ctx.report_service.stock_valuation()
        row = next(r for r in valuation["rows"] if r["product_id"] == product.id)
        assert row["qty"] == 90
        assert row["value"] == Decimal("900.00")
        assert valuation["total_value"] >= Decimal("900.00")

    def test_waste_summary_counts_written_off_units(self, ctx):
        product = _product(ctx)
        ctx.inventory_service.receive_stock(
            product.id, 20, unit_cost=Decimal("10"),
            expiry_date=(date.today() - timedelta(days=1)).isoformat(),
        )
        ctx.inventory_service.record_waste(product.id, 5, reason="Expired")

        waste = ctx.report_service.waste_summary(90)
        assert waste["total_units"] == 5
        assert waste["rows"][0]["name"] == product.name


class TestForecastAndPurchasingReports:
    def test_forecast_accuracy_backtests_products_with_history(self, ctx):
        product = _product(ctx)
        _seed_demand(ctx, product.id)

        accuracy = ctx.report_service.forecast_accuracy()
        assert accuracy["products"], "expected at least one backtested product"
        entry = accuracy["products"][0]
        assert entry["best_method"]
        assert entry["wape"] is not None

    def test_purchasing_summary_lists_open_orders(self, ctx):
        product = _product(ctx)
        ctx.purchase_orders.create(supplier_id=None, items=[(product.id, 12, 10.0)], status="confirmed")

        summary = ctx.report_service.purchasing_summary()
        assert summary["open_count"] == 1
        assert summary["open_value"] == Decimal("120.00")


class TestExport:
    def test_export_csv_writes_file(self, ctx, tmp_path):
        product = _product(ctx)
        ctx.inventory_service.receive_stock(product.id, 5, unit_cost=Decimal("10"))

        target = ctx.report_service.export_csv(
            tmp_path / "valuation.csv",
            ["product_id", "name", "qty"],
            ctx.report_service.stock_valuation()["rows"],
        )
        assert target.exists()
        text = target.read_text(encoding="utf-8")
        assert "product_id,name,qty" in text
        assert product.name in text


class TestReportsView:
    def test_reports_view_builds(self, ctx, wired_app_context):
        from ui.views.reports_view import build_reports_view

        product = _product(ctx, "RV-1")
        ctx.inventory_service.receive_stock(product.id, 10, unit_cost=Decimal("10"))
        ctx.sales_service.record_sale(Sale(items=[SaleItem(product_id=product.id, quantity=2)]))

        control = build_reports_view(page=None, navigate=lambda r: None)
        assert control is not None
