"""StockWise — SQLite repository for stored reorder recommendations."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from repositories.sqlite.base import SqliteRepository


def _row(row: sqlite3.Row) -> dict:
    data = dict(row)
    raw = data.get("rationale_json")
    try:
        data["rationale"] = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data["rationale"] = {}
    return data


class SqliteReorderRepository(SqliteRepository):
    def save(
        self,
        product_id: int,
        *,
        suggested_qty: float,
        estimated_cost: float,
        urgency: str,
        rationale: dict,
        status: str = "pending",
        model_version: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO reorder_recommendations
                   (product_id, suggested_qty, estimated_cost, urgency, rationale_json, status, model_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, float(suggested_qty), float(estimated_cost), urgency,
                 json.dumps(rationale or {}), status, model_version),
            )
            return int(cur.lastrowid)

    def get(self, reco_id: int, conn: sqlite3.Connection | None = None) -> Optional[dict]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM reorder_recommendations WHERE id = ?", (reco_id,)).fetchone()
        return _row(row) if row else None

    def list(self, status: str | None = None, limit: int = 200,
             conn: sqlite3.Connection | None = None) -> list[dict]:
        sql = "SELECT * FROM reorder_recommendations"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn(conn) as c:
            rows = c.execute(sql, params).fetchall()
        return [_row(r) for r in rows]

    def update_status(self, reco_id: int, status: str, reviewed_qty: float | None = None,
                      conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute(
                """UPDATE reorder_recommendations
                   SET status = ?, reviewed_at = datetime('now'),
                       reviewed_qty = COALESCE(?, reviewed_qty)
                   WHERE id = ?""",
                (status, reviewed_qty, reco_id),
            )

    def clear_pending(self, conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute("DELETE FROM reorder_recommendations WHERE status = 'pending'")
