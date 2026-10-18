"""Tests for the SQLite connection factory.

``get_connection`` has two modes and both must behave identically apart from
connection lifetime: a fresh connection per call (the default, used by tests) and
a reused per-thread connection (used by the long-lived desktop app). The reused
mode exists because a cold connection's first query costs ~20ms here, so these
tests pin the guarantees it has to keep — same pragmas, real commit/rollback,
working foreign keys — rather than the speed itself.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
from pathlib import Path

import pytest

from repositories.sqlite.connection import DatabaseConnection
from repositories.sqlite.schema import initialize_database


@pytest.fixture(params=[False, True], ids=["fresh", "reused"])
def db(request):
    """The same connection factory in both modes, so both are held to the same rules."""
    temp_dir = tempfile.mkdtemp()
    connection = DatabaseConnection(
        Path(temp_dir) / "conn_test.db", reuse_connections=request.param
    )
    initialize_database(connection)
    yield connection
    connection.close()


def _insert(conn, sku="A"):
    conn.execute(
        "INSERT INTO products (sku, name, category, unit, cost_price, selling_price, "
        "reorder_point, safety_stock, expiry_tracking, active) "
        "VALUES (?, 'Item', 'Cat', 'pcs', 10, 15, 5, 2, 0, 1)",
        (sku,),
    )


class TestBothModesBehaveTheSame:
    def test_foreign_keys_are_enforced(self, db):
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            # A sale item pointing at a product that does not exist must be refused.
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO sale_items (sale_id, product_id, quantity, unit_price) "
                    "VALUES (999999, 424242, 1, 5)",
                )

    def test_wal_journal_mode_is_active(self, db):
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_rows_are_accessible_by_column_name(self, db):
        with db.get_connection() as conn:
            _insert(conn, sku="BYNAME")
            row = conn.execute("SELECT sku FROM products").fetchone()
            assert row["sku"] == "BYNAME"

    def test_writes_are_committed_on_success(self, db):
        with db.get_connection() as conn:
            _insert(conn, sku="COMMIT")
        assert db.query_one("SELECT sku FROM products WHERE sku='COMMIT'") is not None

    def test_a_failure_rolls_the_whole_transaction_back(self, db):
        with pytest.raises(RuntimeError):
            with db.get_connection() as conn:
                _insert(conn, sku="ROLLBACK")
                raise RuntimeError("simulated failure mid-transaction")
        assert db.query_one("SELECT sku FROM products WHERE sku='ROLLBACK'") is None

    def test_rollback_leaves_the_next_statement_usable(self, db):
        with pytest.raises(RuntimeError):
            with db.get_connection() as conn:
                _insert(conn, sku="ROLLBACK2")
                raise RuntimeError("simulated failure")
        with db.get_connection() as conn:
            _insert(conn, sku="AFTER")
        assert db.query_one("SELECT sku FROM products WHERE sku='AFTER'") is not None


class TestReuseMode:
    @pytest.fixture
    def pooled(self):
        temp_dir = tempfile.mkdtemp()
        connection = DatabaseConnection(
            Path(temp_dir) / "pool_test.db", reuse_connections=True
        )
        initialize_database(connection)
        yield connection
        connection.close()

    def test_the_same_connection_is_handed_back(self, pooled):
        with pooled.get_connection() as first:
            pass
        with pooled.get_connection() as second:
            pass
        assert first is second, "the point of reuse is one connection per thread"

    def test_default_mode_does_not_reuse(self):
        temp_dir = tempfile.mkdtemp()
        connection = DatabaseConnection(Path(temp_dir) / "fresh_test.db")
        initialize_database(connection)
        try:
            with connection.get_connection() as first:
                pass
            with connection.get_connection() as second:
                pass
            assert first is not second
        finally:
            connection.close()

    def test_each_thread_gets_its_own_connection(self, pooled):
        seen: list[int] = []
        barrier = threading.Barrier(2)

        def worker():
            with pooled.get_connection() as conn:
                seen.append(id(conn))
                barrier.wait(timeout=10)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        assert len(seen) == 2 and seen[0] != seen[1], "threads must not share a handle"

    def test_close_releases_the_cached_connection(self, pooled):
        with pooled.get_connection() as first:
            pass
        pooled.close()
        with pooled.get_connection() as second:
            pass
        assert second is not first, "close() must force a fresh connection"

    def test_close_all_releases_every_threads_connection(self, pooled):
        # Hold the connections themselves, not their ids: once close_all() drops
        # them, CPython recycles the addresses and id() comparison is meaningless.
        seen: list = []
        barrier = threading.Barrier(3)

        def worker() -> None:
            with pooled.get_connection() as conn:
                seen.append(conn)
                barrier.wait(timeout=10)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        with pooled.get_connection() as mine:
            seen.append(mine)
            barrier.wait(timeout=10)
        for thread in threads:
            thread.join(timeout=15)

        pooled.close_all()
        with pooled.get_connection() as after:
            pass
        assert after not in seen, "close_all() must drop every cached handle"

    def test_close_all_forces_wal_to_be_reasserted(self, pooled):
        with pooled.get_connection():
            pass
        assert pooled._journal_mode_set is True
        pooled.close_all()
        assert pooled._journal_mode_set is False
        with pooled.get_connection() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_close_all_is_safe_when_nothing_is_open(self, pooled):
        pooled.close_all()
        pooled.close_all()
        with pooled.get_connection() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1

    def test_the_database_can_be_deleted_after_close(self, pooled):
        """Windows refuses to delete an open file, so close() has to really close."""
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / "removable.db"
        connection = DatabaseConnection(path, reuse_connections=True)
        initialize_database(connection)
        with connection.get_connection() as conn:
            _insert(conn, sku="REMOVABLE")
        connection.close()
        path.unlink()
        assert not path.exists()