"""StockWise — SQLite product repository."""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from domain.entities import Product
from domain.money import to_db, to_money
from repositories.sqlite.base import SqliteRepository


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=row["id"],
        sku=row["sku"],
        name=row["name"],
        category=row["category"],
        unit=row["unit"],
        brand=row["brand"],
        cost_price=to_money(row["cost_price"]),
        selling_price=to_money(row["selling_price"]),
        reorder_point=row["reorder_point"],
        safety_stock=row["safety_stock"],
        expiry_tracking=bool(row["expiry_tracking"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqliteProductRepository(SqliteRepository):
    def create(self, product: Product, conn: sqlite3.Connection | None = None) -> Product:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO products
                   (sku, name, category, unit, brand, cost_price, selling_price,
                    reorder_point, safety_stock, expiry_tracking, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product.sku, product.name, product.category, product.unit, product.brand,
                    to_db(product.cost_price), to_db(product.selling_price),
                    product.reorder_point, product.safety_stock,
                    int(product.expiry_tracking), int(product.active),
                ),
            )
            product.id = cur.lastrowid
            row = c.execute("SELECT * FROM products WHERE id = ?", (product.id,)).fetchone()
        return _row_to_product(row)

    def update(self, product: Product, conn: sqlite3.Connection | None = None) -> Product:
        with self._conn(conn) as c:
            c.execute(
                """UPDATE products SET sku=?, name=?, category=?, unit=?, brand=?,
                   cost_price=?, selling_price=?, reorder_point=?, safety_stock=?,
                   expiry_tracking=?, active=?, updated_at=datetime('now')
                   WHERE id=?""",
                (
                    product.sku, product.name, product.category, product.unit, product.brand,
                    to_db(product.cost_price), to_db(product.selling_price),
                    product.reorder_point, product.safety_stock,
                    int(product.expiry_tracking), int(product.active), product.id,
                ),
            )
            row = c.execute("SELECT * FROM products WHERE id = ?", (product.id,)).fetchone()
        return _row_to_product(row)

    def get_by_id(self, product_id: int, conn: sqlite3.Connection | None = None) -> Optional[Product]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _row_to_product(row) if row else None

    def get_by_sku(self, sku: str, conn: sqlite3.Connection | None = None) -> Optional[Product]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        return _row_to_product(row) if row else None

    def list_all(
        self,
        active_only: bool = True,
        category: str | None = None,
        search_query: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> Sequence[Product]:
        sql = "SELECT * FROM products WHERE 1=1"
        params: list = []
        if active_only:
            sql += " AND active = 1"
        if category:
            sql += " AND category = ?"
            params.append(category)
        if search_query:
            sql += " AND (name LIKE ? OR sku LIKE ? OR brand LIKE ?)"
            like = f"%{search_query}%"
            params += [like, like, like]
        sql += " ORDER BY name COLLATE NOCASE"
        with self._conn(conn) as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_product(r) for r in rows]

    def archive(self, product_id: int, conn: sqlite3.Connection | None = None) -> bool:
        with self._conn(conn) as c:
            cur = c.execute(
                "UPDATE products SET active = 0, updated_at = datetime('now') WHERE id = ?",
                (product_id,),
            )
        return cur.rowcount > 0

    def count(self, active_only: bool = True, conn: sqlite3.Connection | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM products" + (" WHERE active = 1" if active_only else "")
        with self._conn(conn) as c:
            return int(c.execute(sql).fetchone()["n"])
