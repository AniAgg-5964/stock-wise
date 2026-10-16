"""StockWise — SQLite audit repository (append-only event log)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional, Sequence

from repositories.sqlite.base import SqliteRepository


class SqliteAuditRepository(SqliteRepository):
    def record_event(
        self,
        event_type: str,
        entity_type: str | None = None,
        entity_id: Any = None,
        details: dict | None = None,
        created_by: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._conn(conn) as c:
            cur = c.execute(
                """INSERT INTO audit_events (event_type, entity_type, entity_id, details_json, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, entity_type,
                 str(entity_id) if entity_id is not None else None,
                 json.dumps(details or {}), created_by),
            )
            return cur.lastrowid

    def list_events(
        self,
        entity_type: str | None = None,
        entity_id: Any = None,
        limit: int = 100,
        conn: sqlite3.Connection | None = None,
    ) -> Sequence[dict]:
        sql = "SELECT * FROM audit_events WHERE 1=1"
        params: list = []
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        if entity_id is not None:
            sql += " AND entity_id = ?"
            params.append(str(entity_id))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn(conn) as c:
            rows = c.execute(sql, params).fetchall()
        events = []
        for r in rows:
            events.append({
                "id": r["id"], "event_type": r["event_type"], "entity_type": r["entity_type"],
                "entity_id": r["entity_id"], "occurred_at": r["occurred_at"],
                "details": json.loads(r["details_json"]) if r["details_json"] else {},
                "created_by": r["created_by"],
            })
        return events
