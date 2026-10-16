"""StockWise — SQLite connection management.

A small connection factory. Each ``get_connection()`` yields a fresh
connection with row access by name, foreign keys enforced, and WAL journal
mode, so callers get safe, well-configured connections without sharing a
single global handle.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import Config


class DatabaseConnection:
    """Creates configured SQLite connections for a given database file."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path: Path = Path(db_path) if db_path is not None else Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection; commit on success, roll back on error."""
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Run a single write statement in its own transaction."""
        with self.get_connection() as conn:
            conn.execute(sql, params)

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.get_connection() as conn:
            return conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute(sql, params).fetchall()
