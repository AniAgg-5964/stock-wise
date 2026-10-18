"""StockWise — SQLite connection management.

A small connection factory. Each ``get_connection()`` yields a connection with row
access by name, foreign keys enforced, and WAL journal mode, so callers get safe,
well-configured connections without having to know the configuration.

**Connection reuse.** Opening a connection is cheap; the *first query* on a cold
connection is not. SQLite keeps no page cache between connections, so every
fresh connection re-reads the schema and re-warms its cache from disk, which
measured ~20ms here versus ~0.4ms on a warm one. A screen issuing a few hundred
queries therefore spent nearly all of its time paying for cold starts.

With ``reuse_connections=True`` each thread keeps one connection open and reuses
it. That is intended for the long-lived, single-user desktop app. It defaults to
off so short-lived callers (notably tests, which create and delete many temporary
databases) keep a fresh connection per call and never hold a deleted file open.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import Config


class DatabaseConnection:
    """Creates configured SQLite connections for a given database file."""

    def __init__(self, db_path: Path | str | None = None, *,
                 reuse_connections: bool = False) -> None:
        self.db_path: Path = Path(db_path) if db_path is not None else Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reuse_connections = bool(reuse_connections)
        # `journal_mode` belongs to the *database file*, not to a connection, so it
        # only needs asserting once. Re-asserting it takes a file lock every time.
        # `foreign_keys` is per-connection and must still be set on each one.
        self._journal_mode_set = False
        # Cached handles keyed by thread id. Reuse is per thread, but the registry
        # is central so `close_all()` can drop every one of them - needed when the
        # database file is replaced underneath a running app.
        self._lock = threading.Lock()
        self._connections: dict[int, sqlite3.Connection] = {}

    def _configure(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._journal_mode_set:
            conn.execute("PRAGMA journal_mode = WAL")
            self._journal_mode_set = True

    def _thread_connection(self) -> sqlite3.Connection:
        """This thread's long-lived connection, created on first use."""
        key = threading.get_ident()
        with self._lock:
            conn = self._connections.get(key)
            if conn is None:
                # check_same_thread is safe to relax because a connection is only
                # ever handed back to the thread registered as its owner.
                conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
                self._configure(conn)
                self._connections[key] = conn
            return conn

    def close(self) -> None:
        """Close this thread's cached connection, if any."""
        with self._lock:
            conn = self._connections.pop(threading.get_ident(), None)
        if conn is not None:
            conn.close()

    def close_all(self) -> None:
        """Close every cached connection, on every thread.

        Required whenever the database file is replaced underneath a running app
        (backup restore). A live connection answers from its own page cache, so
        without this the restore would report success while the app kept showing
        pre-restore data. Also clears the journal-mode flag, because the next
        connection may be opening a different file.
        """
        with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
            self._journal_mode_set = False
        for conn in connections:
            try:
                conn.close()
            except sqlite3.Error:  # pragma: no cover - handle already gone
                pass

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection; commit on success, roll back on error."""
        if not self.reuse_connections:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            try:
                self._configure(conn)
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        conn = self._thread_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------ shortcuts
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