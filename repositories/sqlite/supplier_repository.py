"""StockWise — SQLite supplier repository (suppliers + product-supplier mapping)."""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from domain.entities import ProductSupplier, Supplier
from domain.money import to_db, to_money
from repositories.sqlite.base import SqliteRepository


def _row_to_supplier(row: sqlite3.Row) -> Supplier:
    return Supplier(
        id=row["id"], name=row["name"], contact=row["contact"], email=row["email"],
        phone=row["phone"], website_url=row["website_url"], address=row["address"],
        notes=row["notes"], active=bool(row["active"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _row_to_link(row: sqlite3.Row) -> ProductSupplier:
    return ProductSupplier(
        id=row["id"], product_id=row["product_id"], supplier_id=row["supplier_id"],
        supplier_sku=row["supplier_sku"], lead_time_days=row["lead_time_days"],
        minimum_order_qty=row["minimum_order_qty"], pack_size=row["pack_size"],
        unit_cost=to_money(row["unit_cost"]) if row["unit_cost"] is not None else None,
        is_preferred=bool(row["is_preferred"]), last_verified_at=row["last_verified_at"],
    )


class SqliteSupplierRepository(SqliteRepository):
    def create(self, supplier: Supplier, conn: sqlite3.Connection | None = None) -> Supplier:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO suppliers (name, contact, email, phone, website_url, address, notes, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (supplier.name, supplier.contact, supplier.email, supplier.phone,
                 supplier.website_url, supplier.address, supplier.notes, int(supplier.active)),
            )
            supplier.id = cur.lastrowid
            row = c.execute("SELECT * FROM suppliers WHERE id = ?", (supplier.id,)).fetchone()
        return _row_to_supplier(row)

    def update(self, supplier: Supplier, conn: sqlite3.Connection | None = None) -> Supplier:
        with self._conn(conn) as c:
            c.execute(
                """UPDATE suppliers SET name=?, contact=?, email=?, phone=?, website_url=?,
                   address=?, notes=?, active=?, updated_at=datetime('now') WHERE id=?""",
                (supplier.name, supplier.contact, supplier.email, supplier.phone,
                 supplier.website_url, supplier.address, supplier.notes,
                 int(supplier.active), supplier.id),
            )
            row = c.execute("SELECT * FROM suppliers WHERE id = ?", (supplier.id,)).fetchone()
        return _row_to_supplier(row)

    def get_by_id(self, supplier_id: int, conn: sqlite3.Connection | None = None) -> Optional[Supplier]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        return _row_to_supplier(row) if row else None

    def list_all(self, active_only: bool = True, conn: sqlite3.Connection | None = None) -> Sequence[Supplier]:
        sql = "SELECT * FROM suppliers" + (" WHERE active = 1" if active_only else "") + " ORDER BY name COLLATE NOCASE"
        with self._conn(conn) as c:
            rows = c.execute(sql).fetchall()
        return [_row_to_supplier(r) for r in rows]

    def archive(self, supplier_id: int, conn: sqlite3.Connection | None = None) -> bool:
        with self._conn(conn) as c:
            cur = c.execute(
                "UPDATE suppliers SET active = 0, updated_at = datetime('now') WHERE id = ?",
                (supplier_id,),
            )
        return cur.rowcount > 0

    def link_product_supplier(self, link: ProductSupplier, conn: sqlite3.Connection | None = None) -> ProductSupplier:
        with self._conn(conn) as c:
            c.execute(
                """INSERT INTO product_suppliers
                   (product_id, supplier_id, supplier_sku, lead_time_days, minimum_order_qty,
                    pack_size, unit_cost, is_preferred, last_verified_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(product_id, supplier_id) DO UPDATE SET
                     supplier_sku=excluded.supplier_sku,
                     lead_time_days=excluded.lead_time_days,
                     minimum_order_qty=excluded.minimum_order_qty,
                     pack_size=excluded.pack_size,
                     unit_cost=excluded.unit_cost,
                     is_preferred=excluded.is_preferred,
                     last_verified_at=excluded.last_verified_at,
                     updated_at=datetime('now')""",
                (link.product_id, link.supplier_id, link.supplier_sku, link.lead_time_days,
                 link.minimum_order_qty, link.pack_size, to_db(link.unit_cost),
                 int(link.is_preferred), link.last_verified_at),
            )
            row = c.execute(
                "SELECT * FROM product_suppliers WHERE product_id = ? AND supplier_id = ?",
                (link.product_id, link.supplier_id),
            ).fetchone()
        return _row_to_link(row)

    def get_product_suppliers(self, product_id: int, conn: sqlite3.Connection | None = None) -> Sequence[tuple[ProductSupplier, Supplier]]:
        with self._conn(conn) as c:
            rows = c.execute(
                """SELECT ps.*, s.name AS s_name, s.contact AS s_contact, s.email AS s_email,
                          s.phone AS s_phone, s.website_url AS s_website, s.address AS s_address,
                          s.notes AS s_notes, s.active AS s_active, s.created_at AS s_created,
                          s.updated_at AS s_updated
                   FROM product_suppliers ps JOIN suppliers s ON s.id = ps.supplier_id
                   WHERE ps.product_id = ?
                   ORDER BY ps.is_preferred DESC, ps.lead_time_days ASC""",
                (product_id,),
            ).fetchall()
        result = []
        for r in rows:
            supplier = Supplier(
                id=r["supplier_id"], name=r["s_name"], contact=r["s_contact"], email=r["s_email"],
                phone=r["s_phone"], website_url=r["s_website"], address=r["s_address"],
                notes=r["s_notes"], active=bool(r["s_active"]),
                created_at=r["s_created"], updated_at=r["s_updated"],
            )
            result.append((_row_to_link(r), supplier))
        return result

    def get_preferred_supplier(self, product_id: int, conn: sqlite3.Connection | None = None) -> Optional[tuple[ProductSupplier, Supplier]]:
        links = self.get_product_suppliers(product_id, conn=conn)
        for link, supplier in links:
            if link.is_preferred:
                return link, supplier
        return links[0] if links else None
