"""StockWise — dashboard service.

Builds the dashboard metrics from real data only. Anything that depends on
forecasting (predicted stockouts, demand charts) is intentionally *not*
computed here yet — later stages add it, and the UI shows an honest
"not available" state until then.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from application.dto import DashboardStats


class DashboardService:
    def __init__(self, product_service, inventory_service, sales_repo) -> None:
        self.product_service = product_service
        self.inventory = inventory_service
        self.sales = sales_repo

    def stats(self, *, products=None, snapshots=None) -> DashboardStats:
        """Headline figures for the dashboard.

        ``products`` / ``snapshots`` may be supplied when the caller has already
        read them, so one screen does not rebuild the same inventory snapshot
        several times over.
        """
        if products is None:
            products = list(self.product_service.list_products(active_only=True))
        if snapshots is None:
            snapshots = self.inventory.snapshots_for_products(products)
        by_id = {s.product.id: s for s in snapshots}

        low_statuses = {"low", "out_of_stock"}
        low_items = sorted(
            (s for s in snapshots if s.status in low_statuses),
            key=lambda s: s.usable_stock,
        )

        expiring = []
        for batch in self.inventory.expiring_batches():
            snapshot = by_id.get(batch.product_id)
            product = snapshot.product if snapshot else self.product_service.get_product(batch.product_id)
            if product is not None:
                expiring.append((product, batch))

        recent = []
        for movement in self.inventory.get_movements(limit=8):
            snapshot = by_id.get(movement.product_id)
            product = snapshot.product if snapshot else self.product_service.get_product(movement.product_id)
            if product is not None:
                recent.append((product, movement))

        return DashboardStats(
            total_products=len(products),
            total_stock_value=self.inventory.total_stock_value(),
            low_stock_count=sum(1 for s in snapshots if s.status == "low"),
            out_of_stock_count=sum(1 for s in snapshots if s.status == "out_of_stock"),
            near_expiry_count=len(expiring),
            expired_batch_count=len(self.inventory.expired_batches()),
            sales_today_total=self.sales.total_amount_for_date(date.today().isoformat()),
            low_stock_items=low_items[:8],
            expiring_batches=expiring[:8],
            recent_movements=recent,
        )
