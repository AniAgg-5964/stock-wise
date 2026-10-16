"""Schema tests: table creation, versioning, pragmas, and default settings."""

from __future__ import annotations

import tempfile
from pathlib import Path

from repositories.sqlite.connection import DatabaseConnection
from repositories.sqlite.schema import (
    SCHEMA_VERSION,
    get_schema_version,
    initialize_database,
)

EXPECTED_TABLES = {
    "app_settings",
    "audit_events",
    "daily_demand",
    "external_sources",
    "forecasts",
    "inventory_batches",
    "model_runs",
    "product_suppliers",
    "products",
    "purchase_order_items",
    "purchase_orders",
    "reorder_recommendations",
    "sale_items",
    "sales",
    "schema_version",
    "stock_movements",
    "supplier_observations",
    "suppliers",
}


class TestDatabaseSchema:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = DatabaseConnection(Path(self.temp_dir) / "test_stockwise.db")

    def test_initialize_creates_all_tables(self):
        initialize_database(self.db)
        rows = self.db.query_all("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in rows}
        assert EXPECTED_TABLES <= tables, f"Missing: {EXPECTED_TABLES - tables}"

    def test_schema_version_recorded(self):
        initialize_database(self.db)
        assert get_schema_version(self.db) == SCHEMA_VERSION

    def test_idempotent_initialization(self):
        initialize_database(self.db)
        initialize_database(self.db)  # must not raise or duplicate
        assert get_schema_version(self.db) == SCHEMA_VERSION

    def test_foreign_keys_enabled(self):
        with self.db.get_connection() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_wal_mode_enabled(self):
        with self.db.get_connection() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_default_settings_seeded(self):
        initialize_database(self.db)
        row = self.db.query_one("SELECT value FROM app_settings WHERE key = 'currency'")
        assert row is not None and row["value"] == "INR"

    def test_indexes_created(self):
        initialize_database(self.db)
        rows = self.db.query_all("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row["name"] for row in rows}
        assert "idx_stock_movements_product" in indexes
        assert "uq_sales_source_ref" in indexes

    def test_unique_sales_external_ref_enforced(self):
        initialize_database(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO sales (source, external_ref) VALUES ('csv_import', 'INV-1')")
        import sqlite3
        import pytest

        with pytest.raises(sqlite3.IntegrityError):
            with self.db.get_connection() as conn:
                conn.execute("INSERT INTO sales (source, external_ref) VALUES ('csv_import', 'INV-1')")
