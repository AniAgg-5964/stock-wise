"""StockWise — SQLite purchase-order repository.

Only *confirmed* outstanding orders count as incoming stock (PRD 8.2). Drafts are
recorded but ignored by the reorder engine. Nothing here places orders
automatically \u2014 a purchase order only exists because the owner created it.
"""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from repositories.sqlite.base import SqliteRepository


class SqlitePurchaseOrderRepository(SqliteRepository):
    def create(
        self,
        *,
        supplier_id: int | None,
        items: Sequence[tuple[int, float, float]],
        expected_at: str | None = None,
        notes: str | None = None,
        status: str = "confirmed",
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Create a purchase order with ``(product_id, qty, unit_cost)`` items."""
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO purchase_orders (supplier_id, status, expected_at, notes, confirmed_at)
                   VALUES (?, ?, ?, ?, CASE WHEN ? = 'confirmed' THEN datetime('now') ELSE NULL END)""",
                (supplier_id, status, expected_at, notes, status),
            )
            po_id = int(cur.lastrowid)
            total = 0.0
            for product_id, qty, unit_cost in items:
                c.execute(
                    """INSERT INTO purchase_order_items
                       (purchase_order_id, product_id, ordered_qty, received_qty, unit_cost)
                       VALUES (?, ?, ?, 0, ?)""",
                    (po_id, product_id, float(qty), float(unit_cost or 0)),
                )
                total += float(qty) * float(unit_cost or 0)
            c.execute("UPDATE purchase_orders SET total_amount = ? WHERE id = ?", (total, po_id))
        return po_id

    def confirm(self, po_id: int, conn: sqlite3.Connection | None = None) -> bool:
        with self._conn(conn) as c:
            cur = c.execute(
                """UPDATE purchase_orders
                   SET status = 'confirmed', confirmed_at = datetime('now')
                   WHERE id = ? AND status = 'draft'""",
                (po_id,),
            )
        return cur.rowcount > 0

    def mark_received(self, po_id: int, conn: sqlite3.Connection | None = None) -> bool:
        with self._conn(conn) as c:
            cur = c.execute(
                """UPDATE purchase_orders
                   SET status = 'received', received_at = datetime('now')
                   WHERE id = ?""",
                (po_id,),
            )
        return cur.rowcount > 0

    def confirmed_incoming_qty(self, product_id: int, conn: sqlite3.Connection | None = None) -> float:
        """Outstanding quantity on confirmed (not yet received) orders."""
        with self._conn(conn) as c:
            row = c.execute(
                """SELECT COALESCE(SUM(poi.ordered_qty - poi.received_qty), 0) AS q
                   FROM purchase_order_items poi
                   JOIN purchase_orders po ON po.id = poi.purchase_order_id
                   WHERE poi.product_id = ? AND po.status = 'confirmed'
                     AND poi.ordered_qty > poi.received_qty""",
                (product_id,),
            ).fetchone()
        return float(row["q"]) if row else 0.0

    def list_open(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        with self._conn(conn) as c:
            rows = c.execute(
                """SELECT po.id, po.supplier_id, po.status, po.expected_at, po.notes,
                          po.total_amount, po.created_at, s.name AS supplier_name
                   FROM purchase_orders po LEFT JOIN suppliers s ON s.id = po.supplier_id
                   WHERE po.status IN ('draft', 'confirmed')
                   ORDER BY po.id DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, po_id: int, conn: sqlite3.Connection | None = None) -> Optional[dict]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM purchase_orders WHERE id = ?", (po_id,)).fetchone()
            if not row:
                return None
            items = c.execute(
                """SELECT poi.*, p.name AS product_name FROM purchase_order_items poi
                   LEFT JOIN products p ON p.id = poi.product_id
                   WHERE poi.purchase_order_id = ? ORDER BY poi.id""",
                (po_id,),
            ).fetchall()
        data = dict(row)
        data["items"] = [dict(i) for i in items]
        return data
