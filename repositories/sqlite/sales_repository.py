"""StockWise — SQLite sales repository (sales, items, and daily demand)."""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from domain.entities import Sale, SaleItem
from domain.money import to_db, to_money
from repositories.sqlite.base import SqliteRepository


def _row_to_sale(row: sqlite3.Row) -> Sale:
    return Sale(
        id=row["id"], sold_at=row["sold_at"], source=row["source"],
        external_ref=row["external_ref"], notes=row["notes"],
        total_amount=to_money(row["total_amount"]), created_at=row["created_at"],
    )


def _row_to_item(row: sqlite3.Row, product_name: str | None = None) -> SaleItem:
    return SaleItem(
        id=row["id"], sale_id=row["sale_id"], product_id=row["product_id"],
        quantity=row["quantity"], unit_price=to_money(row["unit_price"]),
        unit_cost_snapshot=(to_money(row["unit_cost_snapshot"]) if row["unit_cost_snapshot"] is not None else None),
        line_total=to_money(row["line_total"]), product_name=product_name,
    )


class SqliteSalesRepository(SqliteRepository):
    def create_sale_header(self, sale: Sale, conn: sqlite3.Connection | None = None) -> Sale:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO sales (sold_at, source, external_ref, notes, total_amount)
                   VALUES (COALESCE(?, datetime('now')), ?, ?, ?, ?)""",
                (sale.sold_at, sale.source, sale.external_ref, sale.notes, to_db(sale.total_amount)),
            )
            sale.id = cur.lastrowid
            row = c.execute("SELECT * FROM sales WHERE id = ?", (sale.id,)).fetchone()
        return _row_to_sale(row)

    def add_item(self, item: SaleItem, conn: sqlite3.Connection | None = None) -> SaleItem:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO sale_items
                   (sale_id, product_id, quantity, unit_price, unit_cost_snapshot, line_total)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item.sale_id, item.product_id, item.quantity, to_db(item.unit_price),
                 to_db(item.unit_cost_snapshot), to_db(item.line_total)),
            )
            item.id = cur.lastrowid
        return item

    def create_sale(self, sale: Sale, conn: sqlite3.Connection | None = None) -> Sale:
        """Insert a sale and its items without stock side-effects (tests/imports)."""
        items = list(sale.items)
        with self._conn(conn) as c:
            header = self.create_sale_header(sale, conn=c)
            for item in items:
                item.sale_id = header.id
                self.add_item(item, conn=c)
            header.items = items
        return header

    def get_sale(self, sale_id: int, conn: sqlite3.Connection | None = None) -> Optional[Sale]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
            if not row:
                return None
            sale = _row_to_sale(row)
            sale.items = list(self.get_items(sale_id, conn=c))
        return sale

    def get_items(self, sale_id: int, conn: sqlite3.Connection | None = None) -> Sequence[SaleItem]:
        with self._conn(conn) as c:
            rows = c.execute(
                """SELECT si.*, p.name AS product_name
                   FROM sale_items si LEFT JOIN products p ON p.id = si.product_id
                   WHERE si.sale_id = ? ORDER BY si.id""",
                (sale_id,),
            ).fetchall()
        return [_row_to_item(r, r["product_name"]) for r in rows]

    def find_by_external_ref(self, source: str, external_ref: str,
                             conn: sqlite3.Connection | None = None) -> Optional[Sale]:
        with self._conn(conn) as c:
            row = c.execute(
                "SELECT * FROM sales WHERE source = ? AND external_ref = ?",
                (source, external_ref),
            ).fetchone()
        return _row_to_sale(row) if row else None

    def list_recent(self, limit: int = 50, conn: sqlite3.Connection | None = None) -> Sequence[Sale]:
        with self._conn(conn) as c:
            rows = c.execute(
                "SELECT * FROM sales ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_sale(r) for r in rows]

    def total_amount_for_date(self, date_str: str, conn: sqlite3.Connection | None = None):
        """Total sales value recorded on a calendar date (``YYYY-MM-DD``)."""
        with self._conn(conn) as c:
            row = c.execute(
                """SELECT COALESCE(SUM(total_amount), 0) AS v FROM sales
                   WHERE substr(sold_at, 1, 10) = ?""",
                (date_str,),
            ).fetchone()
        return to_money(row["v"])

    def record_daily_demand(self, product_id: int, demand_date: str, quantity: float,
                            stockout_flag: bool = False,
                            conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute(
                """INSERT INTO daily_demand (demand_date, product_id, quantity_sold, observed_flag, stockout_flag)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(demand_date, product_id) DO UPDATE SET
                     quantity_sold = daily_demand.quantity_sold + excluded.quantity_sold,
                     stockout_flag = MAX(daily_demand.stockout_flag, excluded.stockout_flag)""",
                (demand_date, product_id, quantity, int(stockout_flag)),
            )
