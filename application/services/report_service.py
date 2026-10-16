"""StockWise \u2014 reporting service (read-only).

Builds the numbers behind the Reports screen and exports them to CSV. Reports are
descriptive (what happened, what stock is worth, how accurate the forecast is) \u2014
they never mutate data.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from domain.money import to_money


class ReportService:
    def __init__(
        self,
        db,
        product_service,
        inventory_service,
        forecast_service,
        purchase_orders,
        product_repo,
    ) -> None:
        self.db = db
        self.products = product_service
        self.inventory = inventory_service
        self.forecasts = forecast_service
        self.purchase_orders = purchase_orders
        self.product_repo = product_repo

    @staticmethod
    def _start(days: int) -> str:
        return (date.today() - timedelta(days=max(1, days) - 1)).isoformat()

    # -------------------------------------------------------------------- sales
    def sales_summary(self, days: int = 30) -> dict:
        start = self._start(days)
        header = self.db.query_one(
            "SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue "
            "FROM sales WHERE date(sold_at) >= ?",
            (start,),
        )
        items = self.db.query_one(
            "SELECT COALESCE(SUM(si.quantity), 0) AS units, "
            "       COALESCE(SUM((si.unit_price - COALESCE(si.unit_cost_snapshot, 0)) * si.quantity), 0) AS margin "
            "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
            "WHERE date(s.sold_at) >= ?",
            (start,),
        )
        return {
            "days": days,
            "start": start,
            "orders": int(header["orders"]) if header else 0,
            "revenue": to_money(header["revenue"] if header else 0),
            "units": float(items["units"]) if items else 0.0,
            "margin": to_money(items["margin"] if items else 0),
        }

    def sales_by_day(self, days: int = 30) -> list[dict]:
        start = self._start(days)
        rows = self.db.query_all(
            "SELECT date(s.sold_at) AS day, "
            "       COALESCE(SUM(s.total_amount), 0) AS revenue, "
            "       COALESCE(SUM((SELECT SUM(si.quantity) FROM sale_items si WHERE si.sale_id = s.id)), 0) AS units "
            "FROM sales s WHERE date(s.sold_at) >= ? GROUP BY day ORDER BY day",
            (start,),
        )
        return [
            {"day": r["day"], "revenue": to_money(r["revenue"]), "units": float(r["units"])}
            for r in rows
        ]

    def top_products(self, days: int = 30, limit: int = 10) -> list[dict]:
        start = self._start(days)
        rows = self.db.query_all(
            "SELECT p.name AS name, SUM(si.quantity) AS qty, SUM(si.line_total) AS revenue "
            "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
            "JOIN products p ON p.id = si.product_id "
            "WHERE date(s.sold_at) >= ? GROUP BY p.id ORDER BY revenue DESC LIMIT ?",
            (start, limit),
        )
        return [{"name": r["name"], "qty": float(r["qty"]), "revenue": to_money(r["revenue"])} for r in rows]

    # ------------------------------------------------------------------- stock
    def stock_valuation(self) -> dict:
        rows = self.db.query_all(
            "SELECT p.id AS product_id, p.name AS name, p.unit AS unit, "
            "  COALESCE(SUM(CASE WHEN b.quantity_remaining > 0 THEN b.quantity_remaining ELSE 0 END), 0) AS qty, "
            "  COALESCE(SUM(CASE WHEN b.quantity_remaining > 0 THEN b.quantity_remaining * COALESCE(b.unit_cost, 0) ELSE 0 END), 0) AS value, "
            "  COALESCE(SUM(CASE WHEN b.quantity_remaining > 0 AND b.expiry_date IS NOT NULL AND b.expiry_date < date('now') "
            "       THEN b.quantity_remaining ELSE 0 END), 0) AS expired_qty, "
            "  COALESCE(SUM(CASE WHEN b.quantity_remaining > 0 AND b.expiry_date IS NOT NULL AND b.expiry_date < date('now') "
            "       THEN b.quantity_remaining * COALESCE(b.unit_cost, 0) ELSE 0 END), 0) AS expired_value "
            "FROM products p LEFT JOIN inventory_batches b ON b.product_id = p.id "
            "GROUP BY p.id ORDER BY value DESC"
        )
        data = [
            {
                "product_id": r["product_id"], "name": r["name"], "unit": r["unit"],
                "qty": float(r["qty"]), "value": to_money(r["value"]),
                "expired_qty": float(r["expired_qty"]), "expired_value": to_money(r["expired_value"]),
            }
            for r in rows
        ]
        return {
            "rows": data,
            "total_value": sum((r["value"] for r in data), start=to_money(0)),
            "total_qty": sum(r["qty"] for r in data),
            "expired_value": sum((r["expired_value"] for r in data), start=to_money(0)),
        }

    def waste_summary(self, days: int = 90) -> dict:
        start = self._start(days)
        rows = self.db.query_all(
            "SELECT p.name AS name, COALESCE(SUM(ABS(sm.quantity_delta)), 0) AS qty "
            "FROM stock_movements sm JOIN products p ON p.id = sm.product_id "
            "WHERE sm.movement_type = 'waste' AND date(sm.occurred_at) >= ? "
            "GROUP BY p.id HAVING qty > 0 ORDER BY qty DESC",
            (start,),
        )
        data = [{"name": r["name"], "qty": float(r["qty"])} for r in rows]
        return {"days": days, "rows": data, "total_units": sum(r["qty"] for r in data)}

    # -------------------------------------------------------------- forecasting
    def forecast_accuracy(self) -> dict:
        status = self.forecasts.model_status()
        products: list[dict] = []
        for product in self.product_repo.list_all(active_only=True):
            metrics = self.forecasts.backtest(product.id)
            if not metrics:
                continue
            best = min(metrics, key=lambda m: m.wape if m.wape is not None else float("inf"))
            products.append({
                "product_id": product.id, "name": product.name,
                "best_method": best.label, "wape": best.wape, "mae": best.mae,
            })
        products.sort(key=lambda r: -(r["wape"] or 0.0))
        return {"model": status, "products": products}

    # -------------------------------------------------------------- purchasing
    def purchasing_summary(self) -> dict:
        open_pos = self.purchase_orders.list_open()
        return {
            "open_count": len(open_pos),
            "open": open_pos,
            "open_value": sum((to_money(po.get("total_amount") or 0) for po in open_pos), start=to_money(0)),
        }

    # ----------------------------------------------------------------- export
    @staticmethod
    def export_csv(target: Path | str, columns: list[str], rows: list[dict]) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([row.get(col, "") for col in columns])
        return target
