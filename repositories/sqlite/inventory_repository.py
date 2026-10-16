"""StockWise — SQLite inventory repository (batches + immutable stock ledger)."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional, Sequence

from domain.entities import InventoryBatch, StockMovement
from domain.money import to_db, to_money
from repositories.sqlite.base import SqliteRepository


def _movement_value(movement_type) -> str:
    """Persist the enum's string value, not ``"MovementType.SALE"``."""
    return movement_type.value if hasattr(movement_type, "value") else str(movement_type)


def _row_to_movement(row: sqlite3.Row) -> StockMovement:
    return StockMovement(
        id=row["id"], product_id=row["product_id"], batch_id=row["batch_id"],
        movement_type=row["movement_type"], quantity_delta=row["quantity_delta"],
        balance_after=row["balance_after"], occurred_at=row["occurred_at"],
        reason=row["reason"], source_type=row["source_type"], source_id=row["source_id"],
        created_by=row["created_by"],
    )


def _row_to_batch(row: sqlite3.Row) -> InventoryBatch:
    return InventoryBatch(
        id=row["id"], product_id=row["product_id"], batch_code=row["batch_code"],
        received_at=row["received_at"], expiry_date=row["expiry_date"],
        quantity_received=row["quantity_received"], quantity_remaining=row["quantity_remaining"],
        unit_cost=to_money(row["unit_cost"]) if row["unit_cost"] is not None else None,
    )


class SqliteInventoryRepository(SqliteRepository):
    # --- Ledger ---
    def add_movement(self, movement: StockMovement, conn: sqlite3.Connection | None = None) -> StockMovement:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO stock_movements
                   (product_id, batch_id, movement_type, quantity_delta, balance_after,
                    occurred_at, reason, source_type, source_id, created_by)
                   VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, ?, ?)""",
                (movement.product_id, movement.batch_id, _movement_value(movement.movement_type),
                 movement.quantity_delta, movement.balance_after, movement.occurred_at,
                 movement.reason, movement.source_type, movement.source_id, movement.created_by),
            )
            movement.id = cur.lastrowid
            row = c.execute("SELECT * FROM stock_movements WHERE id = ?", (movement.id,)).fetchone()
        return _row_to_movement(row)

    def get_stock_movements(self, product_id: int | None = None, limit: int = 100,
                            conn: sqlite3.Connection | None = None) -> Sequence[StockMovement]:
        sql = "SELECT * FROM stock_movements"
        params: list = []
        if product_id is not None:
            sql += " WHERE product_id = ?"
            params.append(product_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn(conn) as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_movement(r) for r in rows]

    def movement_exists(self, source_type: str, source_id: str,
                        movement_type: str | None = None,
                        conn: sqlite3.Connection | None = None) -> bool:
        sql = "SELECT 1 FROM stock_movements WHERE source_type = ? AND source_id = ?"
        params: list = [source_type, str(source_id)]
        if movement_type is not None:
            sql += " AND movement_type = ?"
            params.append(_movement_value(movement_type))
        sql += " LIMIT 1"
        with self._conn(conn) as c:
            return c.execute(sql, params).fetchone() is not None

    def stock_level(self, product_id: int, conn: sqlite3.Connection | None = None) -> float:
        with self._conn(conn) as c:
            row = c.execute(
                "SELECT COALESCE(SUM(quantity_delta), 0) AS s FROM stock_movements WHERE product_id = ?",
                (product_id,),
            ).fetchone()
        return float(row["s"])

    # --- Batches ---
    def create_batch(self, batch: InventoryBatch, conn: sqlite3.Connection | None = None) -> InventoryBatch:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO inventory_batches
                   (product_id, batch_code, received_at, expiry_date, quantity_received,
                    quantity_remaining, unit_cost)
                   VALUES (?, ?, COALESCE(?, datetime('now')), ?, ?, ?, ?)""",
                (batch.product_id, batch.batch_code, batch.received_at, batch.expiry_date,
                 batch.quantity_received, batch.quantity_remaining, to_db(batch.unit_cost)),
            )
            batch.id = cur.lastrowid
            row = c.execute("SELECT * FROM inventory_batches WHERE id = ?", (batch.id,)).fetchone()
        return _row_to_batch(row)

    def get_batch(self, batch_id: int, conn: sqlite3.Connection | None = None) -> Optional[InventoryBatch]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM inventory_batches WHERE id = ?", (batch_id,)).fetchone()
        return _row_to_batch(row) if row else None

    def get_batches_for_product(self, product_id: int, include_depleted: bool = False,
                                conn: sqlite3.Connection | None = None) -> Sequence[InventoryBatch]:
        sql = "SELECT * FROM inventory_batches WHERE product_id = ?"
        if not include_depleted:
            sql += " AND quantity_remaining > 0"
        sql += " ORDER BY (expiry_date IS NULL), expiry_date ASC, received_at ASC, id ASC"
        with self._conn(conn) as c:
            rows = c.execute(sql, (product_id,)).fetchall()
        return [_row_to_batch(r) for r in rows]

    def update_batch_remaining(self, batch_id: int, remaining: float,
                               conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute(
                "UPDATE inventory_batches SET quantity_remaining = ? WHERE id = ?",
                (max(0.0, remaining), batch_id),
            )

    # --- Derived quantities ---
    def usable_stock(self, product_id: int, as_of: str | None = None,
                     conn: sqlite3.Connection | None = None) -> float:
        reference = as_of or date.today().isoformat()
        with self._conn(conn) as c:
            row = c.execute(
                """SELECT COALESCE(SUM(quantity_remaining), 0) AS s FROM inventory_batches
                   WHERE product_id = ? AND quantity_remaining > 0
                     AND (expiry_date IS NULL OR expiry_date >= ?)""",
                (product_id, reference),
            ).fetchone()
        return float(row["s"])

    def total_stock_value(self, conn: sqlite3.Connection | None = None):
        with self._conn(conn) as c:
            row = c.execute(
                """SELECT COALESCE(SUM(quantity_remaining * COALESCE(unit_cost, 0)), 0) AS v
                   FROM inventory_batches WHERE quantity_remaining > 0"""
            ).fetchone()
        return to_money(row["v"])

    def batches_expiring_within(self, days: int, conn: sqlite3.Connection | None = None) -> Sequence[InventoryBatch]:
        today = date.today()
        until = (today + timedelta(days=days)).isoformat()
        with self._conn(conn) as c:
            rows = c.execute(
                """SELECT * FROM inventory_batches
                   WHERE quantity_remaining > 0 AND expiry_date IS NOT NULL
                     AND expiry_date <= ? ORDER BY expiry_date ASC""",
                (until,),
            ).fetchall()
        return [_row_to_batch(r) for r in rows]

    def expired_batches(self, conn: sqlite3.Connection | None = None) -> Sequence[InventoryBatch]:
        today = date.today().isoformat()
        with self._conn(conn) as c:
            rows = c.execute(
                """SELECT * FROM inventory_batches
                   WHERE quantity_remaining > 0 AND expiry_date IS NOT NULL AND expiry_date < ?
                   ORDER BY expiry_date ASC""",
                (today,),
            ).fetchall()
        return [_row_to_batch(r) for r in rows]
