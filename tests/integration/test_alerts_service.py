"""Integration tests for alerts and the expiry screen (real database, real data)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product


def _product(ctx, sku, *, name="Alert Item", reorder_point=10, safety=5):
    return ctx.product_service.create_product(
        Product(sku=sku, name=name, category="Test", unit="pcs",
                cost_price=Decimal("20"), selling_price=Decimal("30"),
                reorder_point=reorder_point, safety_stock=safety)
    )


def _plus_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


class TestAlertsIntegration:
    def test_out_of_stock_and_low_stock_alerts(self, ctx):
        out = _product(ctx, "AL-OUT", name="Empty Item")
        low = _product(ctx, "AL-LOW", name="Low Item")
        ctx.inventory_service.receive_stock(low.id, 4, unit_cost=Decimal("20"))

        kinds = {a.kind: a for a in ctx.alert_service.build()}

        assert kinds["out_of_stock"].product_id == out.id
        assert kinds["low_stock"].product_id == low.id

    def test_near_expiry_and_expiry_risk_alerts(self, ctx):
        product = _product(ctx, "AL-EXP", name="Yoghurt")
        ctx.inventory_service.receive_stock(
            product.id, 30, unit_cost=Decimal("20"), expiry_date=_plus_days(3)
        )

        alerts = ctx.alert_service.build()
        kinds = {a.kind for a in alerts}

        assert "near_expiry" in kinds
        # No sales history -> the whole batch is estimated to expire unsold.
        assert "expiry_risk" in kinds
        risk = next(a for a in alerts if a.kind == "expiry_risk")
        assert risk.product_id == product.id

    def test_expired_batch_is_critical(self, ctx):
        product = _product(ctx, "AL-OLD", name="Old Curd")
        ctx.inventory_service.receive_stock(
            product.id, 6, unit_cost=Decimal("20"), expiry_date=_plus_days(-2)
        )

        expired = [a for a in ctx.alert_service.build() if a.kind == "expired"]

        assert expired and expired[0].severity == "critical"
        assert expired[0].product_id == product.id

    def test_alerts_sorted_critical_first(self, ctx):
        _product(ctx, "AL-S1", name="Empty A")
        _product(ctx, "AL-S2", name="Empty B")

        alerts = ctx.alert_service.build()
        severities = [a.severity for a in alerts]
        assert severities == sorted(severities, key=lambda s: {"critical": 0, "warning": 1, "info": 2}[s])


class TestExpiryViewIntegration:
    def test_expiry_view_builds_with_data(self, ctx, wired_app_context):
        from ui.views.expiry_view import build_expiry_view

        product = _product(ctx, "EV-1", name="Bread")
        ctx.inventory_service.receive_stock(
            product.id, 12, unit_cost=Decimal("20"), expiry_date=_plus_days(2)
        )
        ctx.inventory_service.receive_stock(
            product.id, 5, unit_cost=Decimal("20"), expiry_date=_plus_days(-1)
        )

        control = build_expiry_view(page=None, navigate=lambda r: None)
        assert control is not None

    def test_dashboard_view_builds_with_alerts(self, ctx, wired_app_context):
        from ui.views.dashboard_view import build_dashboard_view

        product = _product(ctx, "DB-1", name="Milk")
        ctx.inventory_service.receive_stock(
            product.id, 2, unit_cost=Decimal("20"), expiry_date=_plus_days(4)
        )

        control = build_dashboard_view(page=None, navigate=lambda r: None)
        assert control is not None
