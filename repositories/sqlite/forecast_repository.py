"""StockWise — SQLite repository for demand history, forecasts and model runs.

Reads the ``daily_demand`` table (written by the sales service) and persists
generated ``forecasts`` plus ``model_runs`` metadata. It never computes
forecasts — that is the ML layer's job.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional, Sequence

from repositories.sqlite.base import SqliteRepository


class SqliteForecastRepository(SqliteRepository):
    # ------------------------------------------------------------ demand history
    def get_demand_history(
        self,
        product_id: int,
        *,
        start: str | None = None,
        end: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[tuple[str, float]]:
        """Return ``(date, quantity)`` pairs, oldest first."""
        sql = "SELECT demand_date, quantity_sold FROM daily_demand WHERE product_id = ?"
        params: list = [product_id]
        if start:
            sql += " AND demand_date >= ?"
            params.append(start)
        if end:
            sql += " AND demand_date <= ?"
            params.append(end)
        sql += " ORDER BY demand_date"
        with self._conn(conn) as c:
            rows = c.execute(sql, tuple(params)).fetchall()
        return [(r["demand_date"], float(r["quantity_sold"])) for r in rows]

    def get_demand_history_full(
        self,
        product_id: int,
        *,
        start: str | None = None,
        end: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[tuple[str, float, bool]]:
        """Return ``(date, quantity, stockout)`` triples, oldest first.

        The stockout flag lets the ML pipeline tell a demand-drop from a day the
        shop had nothing to sell (censored demand).
        """
        sql = (
            "SELECT demand_date, quantity_sold, stockout_flag "
            "FROM daily_demand WHERE product_id = ?"
        )
        params: list = [product_id]
        if start:
            sql += " AND demand_date >= ?"
            params.append(start)
        if end:
            sql += " AND demand_date <= ?"
            params.append(end)
        sql += " ORDER BY demand_date"
        with self._conn(conn) as c:
            rows = c.execute(sql, tuple(params)).fetchall()
        return [
            (r["demand_date"], float(r["quantity_sold"]), bool(r["stockout_flag"]))
            for r in rows
        ]

    def count_demand_days(self, product_id: int, conn: sqlite3.Connection | None = None) -> int:
        with self._conn(conn) as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM daily_demand WHERE product_id = ?", (product_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def list_products_with_demand(self, conn: sqlite3.Connection | None = None) -> list[int]:
        with self._conn(conn) as c:
            rows = c.execute("SELECT DISTINCT product_id FROM daily_demand").fetchall()
        return [int(r["product_id"]) for r in rows]

    def total_demand_by_date(self, start: str, end: str,
                             conn: sqlite3.Connection | None = None) -> list[tuple[str, float]]:
        """Total demand across all products per calendar day (for the dashboard)."""
        with self._conn(conn) as c:
            rows = c.execute(
                """SELECT demand_date, COALESCE(SUM(quantity_sold), 0) AS q
                   FROM daily_demand WHERE demand_date BETWEEN ? AND ?
                   GROUP BY demand_date ORDER BY demand_date""",
                (start, end),
            ).fetchall()
        return [(r["demand_date"], float(r["q"])) for r in rows]

    # ----------------------------------------------------------------- forecasts
    def replace_forecasts(
        self,
        product_id: int,
        points: Sequence[dict],
        *,
        horizon: int,
        model_version: str,
        fallback_used: bool,
        model_run_id: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Replace this product's stored forecasts with ``points`` (atomic).

        Each point is a dict with ``target_date``, ``predicted_qty`` and optional
        ``lower_bound``/``upper_bound``.
        """
        with self._conn(conn) as c:
            c.execute("DELETE FROM forecasts WHERE product_id = ?", (product_id,))
            for point in points:
                c.execute(
                    """INSERT INTO forecasts
                       (product_id, target_date, horizon, predicted_qty, lower_bound,
                        upper_bound, model_version, fallback_used, model_run_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        product_id,
                        point["target_date"],
                        horizon,
                        float(point.get("predicted_qty", 0.0)),
                        point.get("lower_bound"),
                        point.get("upper_bound"),
                        model_version,
                        int(bool(fallback_used)),
                        model_run_id,
                    ),
                )
        return len(points)

    def get_forecasts(self, product_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
        with self._conn(conn) as c:
            rows = c.execute(
                "SELECT * FROM forecasts WHERE product_id = ? ORDER BY target_date",
                (product_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def latest_forecast_meta(self, product_id: int, conn: sqlite3.Connection | None = None) -> Optional[dict]:
        with self._conn(conn) as c:
            row = c.execute(
                "SELECT * FROM forecasts WHERE product_id = ? ORDER BY generated_at DESC LIMIT 1",
                (product_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_forecasts(self, product_id: int, conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute("DELETE FROM forecasts WHERE product_id = ?", (product_id,))

    # ---------------------------------------------------------------- model runs
    def create_model_run(
        self,
        *,
        model_version: str,
        model_type: str,
        metrics: dict | None = None,
        artifact_path: str | None = None,
        train_start: str | None = None,
        train_end: str | None = None,
        feature_schema_version: str | None = None,
        notes: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO model_runs
                   (model_version, model_type, train_start, train_end, metrics_json,
                    artifact_path, feature_schema_version, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_version,
                    model_type,
                    train_start,
                    train_end,
                    json.dumps(metrics or {}),
                    artifact_path,
                    feature_schema_version,
                    notes,
                ),
            )
            return int(cur.lastrowid)

    def get_latest_model_run(self, conn: sqlite3.Connection | None = None) -> Optional[dict]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM model_runs ORDER BY id DESC LIMIT 1").fetchone()
        return _model_run_row(row) if row else None

    def list_model_runs(self, limit: int = 20, conn: sqlite3.Connection | None = None) -> list[dict]:
        with self._conn(conn) as c:
            rows = c.execute("SELECT * FROM model_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_model_run_row(r) for r in rows]


def _model_run_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    raw = data.get("metrics_json")
    if raw:
        try:
            data["metrics"] = json.loads(raw)
        except (ValueError, TypeError):
            data["metrics"] = {}
    else:
        data["metrics"] = {}
    return data
