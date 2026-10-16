"""StockWise — reorder service (periodic-review replenishment).

Turns the forecast plus operational constraints (usable stock, confirmed incoming,
expiry risk, supplier lead time / MOQ / pack, budget) into a deterministic,
explainable recommendation. Recommendations are advisory only \u2014 nothing is
ordered automatically (PRD 8.1).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from app.config import Config
from domain.exceptions import NotFoundError
from domain.money import to_money
from domain.reorder import (
    ReorderContext,
    ReorderRecommendation,
    compute,
    demand_over_period,
    protection_period,
    safety_stock_heuristic,
    safety_stock_statistical,
)
from domain.service_level import parse_service_level, z_for_service_level

logger = logging.getLogger(__name__)

_URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class ReorderService:
    def __init__(
        self,
        db,
        forecast_service,
        inventory_service,
        product_repo,
        supplier_repo,
        purchase_orders,
        reorder_repo,
        settings_repo=None,
        audit_repo=None,
    ) -> None:
        self.db = db
        self.forecast_service = forecast_service
        self.inventory = inventory_service
        self.products = product_repo
        self.suppliers = supplier_repo
        self.purchase_orders = purchase_orders
        self.reorders = reorder_repo
        self.settings = settings_repo
        self.audit = audit_repo

    # ------------------------------------------------------------------- policy
    def _setting_int(self, key: str, default: int) -> int:
        if self.settings is not None:
            value = self.settings.get(key)
            if value:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        return default

    def _review_period(self, override: int | None) -> int:
        return int(override) if override else self._setting_int(
            "review_period_days", Config.DEFAULT_REVIEW_PERIOD_DAYS
        )

    def _safety_buffer_days(self, override: int | None) -> int:
        return int(override) if override is not None else self._setting_int(
            "safety_buffer_days", Config.DEFAULT_SAFETY_BUFFER_DAYS
        )

    def _near_expiry_window(self) -> int:
        return self._setting_int("near_expiry_window_days", Config.NEAR_EXPIRY_WINDOW_DAYS)

    def _safety_policy(self) -> str:
        if self.settings is not None:
            value = (self.settings.get("safety_policy") or "").strip().lower()
            if value in ("heuristic", "statistical"):
                return value
        return Config.DEFAULT_SAFETY_POLICY

    def _service_level(self) -> float:
        value = self.settings.get("service_level") if self.settings is not None else None
        return parse_service_level(value, Config.DEFAULT_SERVICE_LEVEL)

    def _safety_stock(
        self,
        product,
        *,
        avg_daily: float,
        protection_days: int,
        residual_std: float,
        buffer_days_override: int | None,
    ) -> tuple[float, str]:
        """Resolve safety stock under the configured policy; return ``(ss, note)``.

        Statistical (``z x sigma_P``) is used only when demand variability has
        actually been estimated; otherwise it degrades honestly to the heuristic.
        The product's configured minimum safety stock is always respected.
        """
        floor = float(product.safety_stock or 0.0)
        heuristic = safety_stock_heuristic(
            avg_daily, self._safety_buffer_days(buffer_days_override), configured_minimum=floor
        )
        if self._safety_policy() != "statistical":
            return heuristic, ""
        sigma = max(0.0, float(residual_std or 0.0))
        if sigma <= 0:
            return heuristic, (
                "Statistical safety stock requested, but demand variability is not yet "
                "estimated \u2014 used the buffer-days heuristic instead."
            )
        level = self._service_level()
        z = z_for_service_level(level)
        statistical = max(safety_stock_statistical(sigma, protection_days, z), floor)
        return statistical, (
            f"Statistical safety stock for a {level:.0%} service level "
            f"(z={z:g}, \u03c3\u2248{sigma:g}/day over {protection_days} days)."
        )

    def _budget(self, override) -> Decimal | None:
        if override is not None:
            try:
                return to_money(override)
            except (InvalidOperation, ValueError):
                return None
        if self.settings is not None:
            value = self.settings.get("purchase_budget")
            if value:
                try:
                    return to_money(value)
                except (InvalidOperation, ValueError):
                    pass
        return None

    # -------------------------------------------------------------- computation
    def recommend_for_product(
        self,
        product_id: int,
        *,
        budget: Decimal | None = None,
        review_period_days: int | None = None,
        safety_buffer_days: int | None = None,
    ) -> ReorderRecommendation:
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)

        link, supplier = (None, None)
        if self.suppliers is not None:
            link, supplier = self.suppliers.get_preferred_supplier(product_id) or (None, None)

        lead_time = link.lead_time_days if link else Config.DEFAULT_LEAD_TIME_DAYS
        moq = link.minimum_order_qty if link else 1
        pack = link.pack_size if link else 1
        unit_cost = to_money(link.unit_cost) if link and link.unit_cost is not None else to_money(product.cost_price)

        review = self._review_period(review_period_days)
        horizon = protection_period(lead_time, review)

        # --- forecast over the protection period ---
        result = self.forecast_service.latest(product_id)
        if result is None or len(result.points) < horizon:
            result = self.forecast_service.generate(
                product_id, horizon=max(horizon, Config.DEFAULT_FORECAST_HORIZON)
            )
        daily = [p.predicted_qty for p in result.points]
        avg_daily = result.average_daily_demand or (sum(daily) / len(daily) if daily else 0.0)

        usable = self.inventory.usable_stock(product_id)
        incoming = self.purchase_orders.confirmed_incoming_qty(product_id)
        at_risk = self._at_risk_expiry(product_id, daily)

        safety_stock, policy_note = self._safety_stock(
            product,
            avg_daily=avg_daily,
            protection_days=horizon,
            residual_std=getattr(result, "residual_std", 0.0),
            buffer_days_override=safety_buffer_days,
        )

        context = ReorderContext(
            product_id=product.id,
            product_name=product.name,
            unit=product.unit,
            forecast=daily,
            avg_daily_demand=avg_daily,
            usable_on_hand=usable,
            lead_time_days=lead_time,
            review_period_days=review,
            safety_stock=safety_stock,
            confirmed_incoming=incoming,
            at_risk_expiry=at_risk,
            minimum_order_qty=moq,
            pack_size=pack,
            unit_cost=unit_cost,
            budget=self._budget(budget),
            supplier_id=supplier.id if supplier else None,
            supplier_name=supplier.name if supplier else None,
            policy_note=policy_note,
        )
        return compute(context)

    def recommend_all(self, *, budget=None, only_needs_order: bool = True) -> list[ReorderRecommendation]:
        recos = [
            self.recommend_for_product(product.id, budget=budget)
            for product in self.products.list_all(active_only=True)
        ]
        if only_needs_order:
            recos = [r for r in recos if r.needs_order]
        recos.sort(
            key=lambda r: (
                _URGENCY_ORDER.get(r.urgency, 9),
                r.days_to_stockout if r.days_to_stockout is not None else 1e9,
            )
        )
        return recos

    def _at_risk_expiry(self, product_id: int, daily) -> float:
        """Estimate near-expiry units unlikely to sell before they expire."""
        window = self._near_expiry_window()
        today = date.today()
        near_total = 0.0
        for batch in self.inventory.get_batches(product_id):
            if not batch.expiry_date:
                continue
            try:
                expiry = date.fromisoformat(str(batch.expiry_date)[:10])
            except ValueError:
                continue
            days_left = (expiry - today).days
            if 0 <= days_left <= window:
                near_total += batch.quantity_remaining
        if near_total <= 0:
            return 0.0
        expected_sales = demand_over_period(daily, window)
        return max(0.0, near_total - expected_sales)

    # --------------------------------------------------------------- persistence
    def save(self, reco: ReorderRecommendation) -> int:
        return self.reorders.save(
            reco.product_id,
            suggested_qty=reco.suggested_qty,
            estimated_cost=float(reco.estimated_cost),
            urgency=reco.urgency,
            rationale=reco.rationale(),
        )

    def list_saved(self, status: str | None = None) -> list[dict]:
        return self.reorders.list(status)

    def update_status(self, reco_id: int, status: str, reviewed_qty: float | None = None) -> None:
        self.reorders.update_status(reco_id, status, reviewed_qty)

    def create_purchase_order(self, reco: ReorderRecommendation, *, expected_at: str | None = None,
                              actor: str = "system") -> int:
        """Record the order the *owner* decided to place (never automatic)."""
        po_id = self.purchase_orders.create(
            supplier_id=reco.supplier_id,
            items=[(reco.product_id, reco.suggested_qty, float(reco.unit_cost))],
            expected_at=expected_at,
            notes=f"From reorder recommendation for {reco.product_name}",
            status="confirmed",
        )
        if self.audit is not None:
            self.audit.record_event(
                "purchase_order_created", "purchase_order", po_id,
                {"product_id": reco.product_id, "qty": reco.suggested_qty}, actor,
            )
        return po_id
