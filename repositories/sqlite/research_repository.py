"""StockWise — SQLite research repositories (external sources + observations).

Backs the optional TinyFish supplier-research stage. ``supplier_observations``
holds *candidate* facts only; nothing here writes to ``product_suppliers``.
"""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from domain.entities import ExternalSource, SupplierObservation
from repositories.sqlite.base import SqliteRepository


def _row_to_source(row: sqlite3.Row) -> ExternalSource:
    return ExternalSource(
        id=row["id"],
        provider=row["provider"],
        url=row["url"],
        retrieved_at=row["retrieved_at"],
        query=row["query"],
        status_code=row["status_code"],
        parse_status=row["parse_status"] or "pending",
        content_hash=row["content_hash"],
    )


def _row_to_observation(row: sqlite3.Row) -> SupplierObservation:
    return SupplierObservation(
        id=row["id"],
        source_id=row["source_id"],
        supplier_id=row["supplier_id"],
        product_id=row["product_id"],
        field_name=row["field_name"],
        field_value=row["field_value"],
        currency=row["currency"],
        confidence=row["confidence"],
        verified_by_user=bool(row["verified_by_user"]),
        observed_at=row["observed_at"],
    )


class SqliteExternalSourceRepository(SqliteRepository):
    def create(self, source: ExternalSource, conn: sqlite3.Connection | None = None) -> ExternalSource:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO external_sources
                   (provider, url, retrieved_at, query, status_code, parse_status, content_hash)
                   VALUES (?, ?, COALESCE(?, datetime('now')), ?, ?, ?, ?)""",
                (source.provider, source.url, source.retrieved_at, source.query,
                 source.status_code, source.parse_status, source.content_hash),
            )
            source.id = cur.lastrowid
            row = c.execute("SELECT * FROM external_sources WHERE id = ?", (source.id,)).fetchone()
        return _row_to_source(row)

    def get_by_id(self, source_id: int, conn: sqlite3.Connection | None = None) -> Optional[ExternalSource]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM external_sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_source(row) if row else None

    def find_recent_by_url(self, url: str, within_minutes: int,
                           conn: sqlite3.Connection | None = None) -> Optional[ExternalSource]:
        """Return a source fetched from ``url`` within the cache window, if any."""
        with self._conn(conn) as c:
            row = c.execute(
                """SELECT * FROM external_sources
                   WHERE url = ? AND parse_status = 'ok'
                     AND retrieved_at >= datetime('now', ?)
                   ORDER BY id DESC LIMIT 1""",
                (url, f"-{int(within_minutes)} minutes"),
            ).fetchone()
        return _row_to_source(row) if row else None

    def set_parse_status(self, source_id: int, parse_status: str, content_hash: str | None = None,
                         conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute(
                """UPDATE external_sources
                   SET parse_status = ?, content_hash = COALESCE(?, content_hash)
                   WHERE id = ?""",
                (parse_status, content_hash, source_id),
            )

    def list_by_query(self, query: str, limit: int = 20,
                      conn: sqlite3.Connection | None = None) -> Sequence[ExternalSource]:
        with self._conn(conn) as c:
            rows = c.execute(
                "SELECT * FROM external_sources WHERE query = ? ORDER BY id DESC LIMIT ?",
                (query, int(limit)),
            ).fetchall()
        return [_row_to_source(r) for r in rows]

    def count(self, conn: sqlite3.Connection | None = None) -> int:
        with self._conn(conn) as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM external_sources").fetchone()["n"])


class SqliteSupplierObservationRepository(SqliteRepository):
    def create_many(self, observations: Sequence[SupplierObservation],
                    conn: sqlite3.Connection | None = None) -> list[SupplierObservation]:
        if not observations:
            return []
        with self._conn(conn) as c:
            for obs in observations:
                cur = c.execute(
                    """INSERT INTO supplier_observations
                       (source_id, supplier_id, product_id, field_name, field_value,
                        currency, confidence, verified_by_user, observed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))""",
                    (obs.source_id, obs.supplier_id, obs.product_id, obs.field_name,
                     obs.field_value, obs.currency, float(obs.confidence),
                     int(obs.verified_by_user), obs.observed_at),
                )
                obs.id = cur.lastrowid
            rows = c.execute(
                f"SELECT * FROM supplier_observations WHERE id IN ({','.join('?' * len(observations))})",
                [o.id for o in observations],
            ).fetchall()
        by_id = {r["id"]: r for r in rows}
        return [_row_to_observation(by_id[o.id]) for o in observations if o.id in by_id]

    def get_by_id(self, observation_id: int,
                  conn: sqlite3.Connection | None = None) -> Optional[SupplierObservation]:
        with self._conn(conn) as c:
            row = c.execute("SELECT * FROM supplier_observations WHERE id = ?", (observation_id,)).fetchone()
        return _row_to_observation(row) if row else None

    def list_for_product(self, product_id: int, only_unverified: bool = False,
                         conn: sqlite3.Connection | None = None) -> Sequence[SupplierObservation]:
        sql = "SELECT * FROM supplier_observations WHERE product_id = ?"
        if only_unverified:
            sql += " AND verified_by_user = 0"
        sql += " ORDER BY confidence DESC, id DESC"
        with self._conn(conn) as c:
            rows = c.execute(sql, (product_id,)).fetchall()
        return [_row_to_observation(r) for r in rows]

    def list_for_source(self, source_id: int,
                        conn: sqlite3.Connection | None = None) -> Sequence[SupplierObservation]:
        with self._conn(conn) as c:
            rows = c.execute(
                "SELECT * FROM supplier_observations WHERE source_id = ? ORDER BY confidence DESC",
                (source_id,),
            ).fetchall()
        return [_row_to_observation(r) for r in rows]

    def list_recent(self, limit: int = 50,
                    conn: sqlite3.Connection | None = None) -> Sequence[SupplierObservation]:
        with self._conn(conn) as c:
            rows = c.execute(
                "SELECT * FROM supplier_observations ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [_row_to_observation(r) for r in rows]

    def mark_verified(self, observation_id: int, verified: bool = True,
                      conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute(
                "UPDATE supplier_observations SET verified_by_user = ? WHERE id = ?",
                (int(verified), observation_id),
            )

    def delete(self, observation_id: int, conn: sqlite3.Connection | None = None) -> bool:
        with self._conn(conn) as c:
            cur = c.execute("DELETE FROM supplier_observations WHERE id = ?", (observation_id,))
        return cur.rowcount > 0

    def count(self, conn: sqlite3.Connection | None = None) -> int:
        with self._conn(conn) as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM supplier_observations").fetchone()["n"])