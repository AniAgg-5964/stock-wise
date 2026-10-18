"""Unit tests for the alerts ranking logic (stubbed inputs, no database)."""

from __future__ import annotations

from decimal import Decimal

from application.dto import ForecastPoint, ForecastResult, ProductStock
from application.services.alert_service import AlertsService
from domain.entities import Product


def _product(pid=1, name="Test Item", *, reorder_point=10):
    return Product(
        id=pid, sku=f"SKU-{pid}", name=name, category="Test", unit="pcs",
        cost_price=Decimal("10"), selling_price=Decimal("15"), reorder_point=reorder_point,
    )


class _StubProducts:
    def __init__(self, products):
        self._products = products

    def list_all(self, active_only=True):
        return list(self._products)

    def get_by_id(self, pid):
        return next((p for p in self._products if p.id == pid), None)


class _StubInventory:
    def __init__(self, snapshots, batches=None):
        self._snapshots = snapshots
        self._batches = batches or {}

    def snapshots_for_products(self, products):
        return list(self._snapshots)

    def expiring_batches(self, days):
        return []

    def get_batches(self, product_id, **kwargs):
        return list(self._batches.get(product_id, []))


class _StubForecast:
    def __init__(self, latest=None, averages=None):
        self._latest = latest or {}
        self._averages = averages or {}

    def latest(self, product_id):
        return self._latest.get(product_id)

    def latest_for_products(self, product_ids):
        return {
            pid: self._latest[pid] for pid in product_ids if pid in self._latest
        }

    def average_daily_demand(self, product_id, window=28):
        return self._averages.get(product_id, 0.0)


def _snapshot(product, status, usable):
    return ProductStock(product=product, stock_level=usable, usable_stock=usable, status=status)


class TestStockAlerts:
    def test_out_of_stock_is_critical(self):
        product = _product()
        service = AlertsService(
            _StubProducts([product]),
            _StubInventory([_snapshot(product, "out_of_stock", 0.0)]),
            _StubForecast(),
        )
        alerts = service.build()
        assert alerts and alerts[0].kind == "out_of_stock"
        assert alerts[0].severity == "critical"

    def test_low_stock_is_warning(self):
        product = _product()
        service = AlertsService(
            _StubProducts([product]),
            _StubInventory([_snapshot(product, "low", 4.0)]),
            _StubForecast(),
        )
        alerts = service.build()
        assert alerts[0].kind == "low_stock"
        assert alerts[0].severity == "warning"


class TestDemandSpike:
    def test_spike_detected_when_forecast_exceeds_recent(self):
        product = _product()
        latest = ForecastResult(
            product_id=1, product_name="Test Item", horizon=7, method="mean",
            method_label="Mean", average_daily_demand=5.0,
            points=[ForecastPoint(target_date=f"2026-01-{d:02d}", predicted_qty=20.0)
                    for d in range(1, 8)],
        )
        service = AlertsService(
            _StubProducts([product]),
            _StubInventory([_snapshot(product, "healthy", 100.0)]),
            _StubForecast(latest={1: latest}, averages={1: 5.0}),
        )
        alerts = service.build()
        spikes = [a for a in alerts if a.kind == "demand_spike"]
        assert spikes and "rising" in spikes[0].title.lower()

    def test_no_spike_when_forecast_matches_recent(self):
        product = _product()
        latest = ForecastResult(
            product_id=1, product_name="Test Item", horizon=7, method="mean",
            method_label="Mean", average_daily_demand=5.0,
            points=[ForecastPoint(target_date=f"2026-01-{d:02d}", predicted_qty=5.0)
                    for d in range(1, 8)],
        )
        service = AlertsService(
            _StubProducts([product]),
            _StubInventory([_snapshot(product, "healthy", 100.0)]),
            _StubForecast(latest={1: latest}, averages={1: 5.0}),
        )
        assert not [a for a in service.build() if a.kind == "demand_spike"]
