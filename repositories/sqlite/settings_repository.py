"""StockWise — SQLite app-settings repository (non-secret preferences only)."""

from __future__ import annotations

import sqlite3
from typing import Optional

from repositories.sqlite.base import SqliteRepository


class SqliteSettingsRepository(SqliteRepository):
    def get(self, key: str, default: Optional[str] = None,
            conn: sqlite3.Connection | None = None) -> Optional[str]:
        with self._conn(conn) as c:
            row = c.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str, conn: sqlite3.Connection | None = None) -> None:
        with self._conn(conn) as c:
            c.execute(
                """INSERT INTO app_settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')""",
                (key, str(value)),
            )

    def all(self, conn: sqlite3.Connection | None = None) -> dict[str, str]:
        with self._conn(conn) as c:
            rows = c.execute("SELECT key, value FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
