"""Tests for backup and restore.

Restore is the one operation that replaces the database file while the app is
still running, which is exactly where connection reuse can go wrong: a live
connection keeps answering from its own page cache, so the restore reports
success while the app carries on showing pre-restore data. These tests run in
both connection modes, and also pin that a restore drops the memoised demand
reads, because the restored file carries a different history.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Config
from application.services.backup_service import BackupService
from application.services.forecast_service import ForecastService
from domain.exceptions import NotFoundError
from repositories.sqlite.connection import DatabaseConnection
from repositories.sqlite.forecast_repository import SqliteForecastRepository
from repositories.sqlite.product_repository import SqliteProductRepository
from repositories.sqlite.schema import initialize_database
from repositories.sqlite.settings_repository import SqliteSettingsRepository


def _forecast_service(db) -> ForecastService:
    return ForecastService(
        db,
        SqliteForecastRepository(db),
        SqliteProductRepository(db),
        SqliteSettingsRepository(db),
    )


@pytest.fixture(params=[False, True], ids=["fresh", "reused"])
def store(request, tmp_path, monkeypatch):
    """A backup service over an isolated database, in either connection mode.

    ``Config.DB_PATH`` is redirected because ``restore_backup`` targets it
    directly; left alone this would overwrite the real app database.
    """
    db_path = tmp_path / "restore.db"
    monkeypatch.setattr(Config, "DB_PATH", db_path)
    monkeypatch.setattr(Config, "BACKUP_DIR", tmp_path / "backups")

    db = DatabaseConnection(db_path, reuse_connections=request.param)
    initialize_database(db)
    forecasts = _forecast_service(db)
    yield SimpleNamespace(
        db=db,
        db_path=db_path,
        forecasts=forecasts,
        service=BackupService(db, forecasts),
    )
    db.close_all()


def _add_product(db, sku: str) -> int:
    with db.get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO products (sku, name, category, unit, cost_price, selling_price,"
            " reorder_point, safety_stock, expiry_tracking, active)"
            " VALUES (?, 'Item', 'Cat', 'pcs', 10, 15, 5, 2, 0, 1)",
            (sku,),
        )
        return cursor.lastrowid


def _add_demand(db, product_id: int, when: str, quantity: float) -> None:
    db.execute(
        "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?, ?, ?)",
        (when, product_id, quantity),
    )


def _skus(db) -> list[str]:
    return [row["sku"] for row in db.query_all("SELECT sku FROM products ORDER BY sku")]


class TestCreateBackup:
    def test_it_captures_committed_data(self, store):
        _add_product(store.db, "A")
        target = store.service.create_backup()
        assert target.exists()
        # Readable entirely on its own, without the live database.
        reader = sqlite3.connect(str(target))
        try:
            assert reader.execute("SELECT sku FROM products").fetchall() == [("A",)]
        finally:
            reader.close()


class TestRestore:
    def test_the_running_app_sees_the_restored_data(self, store):
        """The regression this file exists for.

        With a reused connection still open, the copy used to land underneath a
        live page cache and the app went on showing pre-restore rows.
        """
        _add_product(store.db, "A")
        backup = store.service.create_backup()
        _add_product(store.db, "B")
        assert _skus(store.db) == ["A", "B"]

        store.service.restore_backup(backup)

        assert _skus(store.db) == ["A"]

    def test_it_agrees_with_an_independent_reader(self, store):
        _add_product(store.db, "A")
        backup = store.service.create_backup()
        _add_product(store.db, "B")
        store.service.restore_backup(backup)

        other = DatabaseConnection(store.db_path)
        try:
            assert _skus(other) == ["A"]
            assert _skus(store.db) == _skus(other)
        finally:
            other.close()

    def test_the_database_is_usable_again_afterwards(self, store):
        _add_product(store.db, "A")
        backup = store.service.create_backup()
        store.service.restore_backup(backup)

        _add_product(store.db, "C")
        assert _skus(store.db) == ["A", "C"]
        assert store.db.query_one("PRAGMA journal_mode")[0] == "wal"
        assert store.db.query_one("PRAGMA foreign_keys")[0] == 1

    def test_it_does_not_leave_the_old_wal_side_files_behind(self, store):
        _add_product(store.db, "A")
        backup = store.service.create_backup()
        _add_product(store.db, "B")
        store.service.restore_backup(backup)

        # Left in place, these belong to the replaced database and SQLite could
        # replay them over the restored file.
        for suffix in ("-wal", "-shm"):
            assert not Path(f"{store.db_path}{suffix}").exists()

    def test_a_missing_file_is_reported(self, store):
        with pytest.raises(NotFoundError):
            store.service.restore_backup(store.db_path.parent / "does-not-exist.db")

    def test_it_works_without_a_forecast_service(self, tmp_path, monkeypatch):
        """The forecast service is optional; restore must not depend on it."""
        db_path = tmp_path / "plain.db"
        monkeypatch.setattr(Config, "DB_PATH", db_path)
        monkeypatch.setattr(Config, "BACKUP_DIR", tmp_path / "backups")
        db = DatabaseConnection(db_path, reuse_connections=True)
        initialize_database(db)
        try:
            service = BackupService(db)
            _add_product(db, "A")
            backup = service.create_backup()
            _add_product(db, "B")
            service.restore_backup(backup)
            assert _skus(db) == ["A"]
        finally:
            db.close_all()


class TestRestoreAndTheDemandCache:
    """A restore rewrites ``daily_demand``, so memoised reads must be dropped."""

    def test_restore_drops_the_memoised_demand_reads(self, store):
        product_id = _add_product(store.db, "A")
        today = date.today().isoformat()
        _add_demand(store.db, product_id, today, 10)
        backup = store.service.create_backup()

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _add_demand(store.db, product_id, yesterday, 5)

        before = store.forecasts.demand_series(product_id)
        assert [point.quantity for point in before] == [5.0, 10.0]
        assert store.forecasts._series_cache, "the series should be memoised"

        store.service.restore_backup(backup)

        assert not store.forecasts._series_cache, (
            "a restore replaces daily_demand, so every memoised read is stale"
        )
        after = store.forecasts.demand_series(product_id)
        assert [point.quantity for point in after] == [10.0]
