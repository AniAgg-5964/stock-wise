"""StockWise — alerts service.

Builds a ranked list of actionable alerts from real data only: out-of-stock and
low stock, batches near or past expiry, estimated expiry risk (waste that is
likely but not yet real), and demand spikes (forecast vs recent actual).
Read-only \u2014 it never generates forecasts or mutates stock.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import Config
from app.i18n import t
from application.dto import Alert

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
_DEMAND_SPIKE_RATIO = 1.5
_DEMAND_SPIKE_MIN_AVG = 1.0


def _days_left(expiry: str | None) -> int | None:
    if not expiry:
        return None
    try:
        return (date.fromisoformat(str(expiry)[:10]) - date.today()).days
    except ValueError:
        return None


class AlertsService:
    def __init__(self, product_repo, inventory_service, forecast_service, settings_repo=None) -> None:
        self.products = product_repo
        self.inventory = inventory_service
        self.forecasts = forecast_service
        self.settings = settings_repo

    def _window(self) -> int:
        if self.settings is not None:
            value = self.settings.get("near_expiry_window_days")
            if value:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        return Config.NEAR_EXPIRY_WINDOW_DAYS

    def build(self, limit: int = 12, *, products=None, snapshots=None) -> list[Alert]:
        """Ranked alerts, most severe first.

        ``products`` / ``snapshots`` may be supplied by a caller that has already
        read them, so a dashboard renders the same inventory snapshot once instead
        of once per panel.
        """
        if products is None:
            products = list(self.products.list_all(active_only=True))
        alerts: list[Alert] = []
        alerts.extend(self._stock_alerts(products, snapshots))
        alerts.extend(self._expiry_alerts(products))
        alerts.extend(self._demand_spike_alerts(products))
        alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 9))
        return alerts[:limit]

    # ------------------------------------------------------------------ builders
    def _stock_alerts(self, products, snapshots=None) -> list[Alert]:
        if snapshots is None:
            snapshots = self.inventory.snapshots_for_products(products)
        alerts: list[Alert] = []
        for snap in snapshots:
            if snap.status == "out_of_stock":
                alerts.append(Alert(
                    "out_of_stock", "critical",
                    t("alert.out_of_stock", name=snap.product.name),
                    t("alert.no_usable", point=snap.product.reorder_point),
                    "/inventory", snap.product.id,
                ))
            elif snap.status == "low":
                alerts.append(Alert(
                    "low_stock", "warning",
                    t("alert.low_stock", name=snap.product.name),
                    t("alert.usable_point", usable=snap.usable_stock,
                      point=snap.product.reorder_point),
                    "/inventory", snap.product.id,
                ))
        return alerts

    def _expiry_alerts(self, products) -> list[Alert]:
        alerts: list[Alert] = []
        window = self._window()
        for batch in self.inventory.expiring_batches(window):
            product = self.products.get_by_id(batch.product_id)
            name = product.name if product else f"Product {batch.product_id}"
            left = _days_left(batch.expiry_date)
            detail = t("alert.batch_detail", qty=batch.quantity_remaining,
                                      batch=batch.batch_code or batch.id)
            if left is not None and left < 0:
                alerts.append(Alert(
                    "expired", "critical",
                    t("alert.expired_ago", name=name, days=abs(left)),
                    t("alert.not_sellable_write_off", detail=detail),
                    "/expiry", batch.product_id,
                ))
            else:
                title = (t("alert.expires_in", name=name, days=left) if left is not None
                         else t("alert.near_expiry", name=name))
                alerts.append(Alert(
                    "near_expiry", "warning", title, detail, "/expiry", batch.product_id,
                ))

        for product in products:
            at_risk = self._at_risk_expiry(product.id, window)
            if at_risk > 0:
                alerts.append(Alert(
                    "expiry_risk", "warning",
                    t("alert.at_risk", at_risk=at_risk, unit=product.unit, name=product.name),
                    t("alert.unsold_markdown"),
                    "/expiry", product.id,
                ))
        return alerts

    def _at_risk_expiry(self, product_id: int, window: int) -> float:
        today = date.today()
        near_total = 0.0
        for batch in self.inventory.get_batches(product_id):
            left = _days_left(batch.expiry_date)
            if left is not None and 0 <= left <= window:
                near_total += batch.quantity_remaining
        if near_total <= 0:
            return 0.0

        latest = self.forecasts.latest(product_id)
        if latest is not None and latest.points:
            daily = [p.predicted_qty for p in latest.points]
        else:
            avg = self.forecasts.average_daily_demand(product_id)
            daily = [avg] * window
        expected_sales = sum(daily[:window])
        return max(0.0, near_total - expected_sales)

    def _demand_spike_alerts(self, products) -> list[Alert]:
        alerts: list[Alert] = []
        # One batched forecast read for every product, instead of one query each.
        forecasts = self.forecasts.latest_for_products([p.id for p in products])
        for product in products:
            latest = forecasts.get(product.id)
            if latest is None or not latest.points:
                continue
            recent = self.forecasts.average_daily_demand(product.id)
            forecast_avg = sum(p.predicted_qty for p in latest.points[:7]) / max(1, min(7, len(latest.points)))
            if recent >= _DEMAND_SPIKE_MIN_AVG and forecast_avg > recent * _DEMAND_SPIKE_RATIO:
                pct = (forecast_avg / recent - 1.0) * 100.0
                alerts.append(Alert(
                    "demand_spike", "info",
                    t("alert.demand_rising", name=product.name),
                    t("alert.demand_rising_msg", pct=pct),
                    "/forecasting", product.id,
                ))
        return alerts
