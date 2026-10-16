"""StockWise — shared SQLite repository base."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from repositories.sqlite.connection import DatabaseConnection


class SqliteRepository:
    """Base class giving repositories access to configured connections.

    Methods accept an optional ``conn`` so a service can compose several writes
    into a single transaction. When ``conn`` is omitted, the repository opens
    its own connection.
    """

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db

    @contextmanager
    def _conn(self, conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
        if conn is not None:
            yield conn
        else:
            with self.db.get_connection() as fresh:
                yield fresh
