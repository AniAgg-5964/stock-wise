"""StockWise — Database schema and migrations.

All tables are created idempotently (``CREATE TABLE IF NOT EXISTS``) and the
schema is versioned via the ``schema_version`` table. Bump ``SCHEMA_VERSION``
and add a forward migration rather than altering tables in place.

Tables (per the PRD data model):
    products, suppliers, product_suppliers            (catalogue)
    sales, sale_items, stock_movements                (transactions / ledger)
    inventory_batches                                 (expiry tracking)
    purchase_orders, purchase_order_items             (incoming stock)
    daily_demand, forecasts, model_runs               (ML)
    reorder_recommendations                           (decisions)
    external_sources, supplier_observations           (TinyFish research)
    app_settings, audit_events, schema_version        (system)

Money columns are stored as REAL (a SQLite limitation); currency arithmetic is
performed with ``Decimal`` at the service layer to avoid float drift.
"""

from __future__ import annotations

import logging

from repositories.sqlite.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Increment when adding a forward migration.
SCHEMA_VERSION = 1


TABLES: list[str] = [
    # --- System ---
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version INTEGER NOT NULL,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
        details_json TEXT,
        created_by TEXT
    )
    """,
    # --- Catalogue ---
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        unit TEXT NOT NULL DEFAULT 'pcs',
        brand TEXT,
        cost_price REAL NOT NULL DEFAULT 0,
        selling_price REAL NOT NULL DEFAULT 0,
        reorder_point INTEGER NOT NULL DEFAULT 10,
        safety_stock INTEGER NOT NULL DEFAULT 5,
        expiry_tracking INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT,
        email TEXT,
        phone TEXT,
        website_url TEXT,
        address TEXT,
        notes TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
        supplier_sku TEXT,
        lead_time_days INTEGER NOT NULL DEFAULT 3,
        minimum_order_qty INTEGER NOT NULL DEFAULT 1,
        pack_size INTEGER NOT NULL DEFAULT 1,
        unit_cost REAL,
        is_preferred INTEGER NOT NULL DEFAULT 0,
        last_verified_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (product_id, supplier_id)
    )
    """,
    # --- Batches & transactions ---
    """
    CREATE TABLE IF NOT EXISTS inventory_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        batch_code TEXT,
        received_at TEXT NOT NULL DEFAULT (datetime('now')),
        expiry_date TEXT,
        quantity_received REAL NOT NULL DEFAULT 0,
        quantity_remaining REAL NOT NULL DEFAULT 0,
        unit_cost REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sold_at TEXT NOT NULL DEFAULT (datetime('now')),
        source TEXT NOT NULL DEFAULT 'manual',
        external_ref TEXT,
        notes TEXT,
        total_amount REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
        product_id INTEGER NOT NULL REFERENCES products(id),
        quantity REAL NOT NULL,
        unit_price REAL NOT NULL DEFAULT 0,
        unit_cost_snapshot REAL,
        line_total REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        batch_id INTEGER REFERENCES inventory_batches(id),
        movement_type TEXT NOT NULL,
        quantity_delta REAL NOT NULL,
        balance_after REAL NOT NULL,
        occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
        reason TEXT,
        source_type TEXT,
        source_id TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # --- Purchase orders (incoming stock; advisory only) ---
    """
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER REFERENCES suppliers(id),
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expected_at TEXT,
        confirmed_at TEXT,
        received_at TEXT,
        notes TEXT,
        total_amount REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
        product_id INTEGER NOT NULL REFERENCES products(id),
        ordered_qty REAL NOT NULL DEFAULT 0,
        received_qty REAL NOT NULL DEFAULT 0,
        unit_cost REAL NOT NULL DEFAULT 0
    )
    """,
    # --- ML ---
    """
    CREATE TABLE IF NOT EXISTS daily_demand (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        demand_date TEXT NOT NULL,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        quantity_sold REAL NOT NULL DEFAULT 0,
        observed_flag INTEGER NOT NULL DEFAULT 1,
        stockout_flag INTEGER NOT NULL DEFAULT 0,
        UNIQUE (demand_date, product_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_version TEXT NOT NULL,
        model_type TEXT,
        trained_at TEXT NOT NULL DEFAULT (datetime('now')),
        train_start TEXT,
        train_end TEXT,
        validation_start TEXT,
        validation_end TEXT,
        test_start TEXT,
        test_end TEXT,
        metrics_json TEXT,
        artifact_path TEXT,
        feature_schema_version TEXT,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        target_date TEXT NOT NULL,
        generated_at TEXT NOT NULL DEFAULT (datetime('now')),
        horizon INTEGER NOT NULL DEFAULT 7,
        predicted_qty REAL NOT NULL,
        lower_bound REAL,
        upper_bound REAL,
        model_version TEXT,
        fallback_used INTEGER NOT NULL DEFAULT 0,
        model_run_id INTEGER REFERENCES model_runs(id)
    )
    """,
    # --- Decisions ---
    """
    CREATE TABLE IF NOT EXISTS reorder_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        generated_at TEXT NOT NULL DEFAULT (datetime('now')),
        suggested_qty REAL NOT NULL DEFAULT 0,
        estimated_cost REAL NOT NULL DEFAULT 0,
        urgency TEXT,
        rationale_json TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        reviewed_at TEXT,
        reviewed_qty REAL,
        model_version TEXT
    )
    """,
    # --- TinyFish research ---
    """
    CREATE TABLE IF NOT EXISTS external_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        url TEXT,
        retrieved_at TEXT NOT NULL DEFAULT (datetime('now')),
        query TEXT,
        status_code INTEGER,
        parse_status TEXT,
        content_hash TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER REFERENCES external_sources(id) ON DELETE CASCADE,
        supplier_id INTEGER REFERENCES suppliers(id),
        product_id INTEGER REFERENCES products(id),
        field_name TEXT NOT NULL,
        field_value TEXT,
        currency TEXT,
        confidence REAL,
        verified_by_user INTEGER NOT NULL DEFAULT 0,
        observed_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
]


INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_products_active ON products(active)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_occurred ON stock_movements(occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_sale_items_product ON sale_items(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at)",
    "CREATE INDEX IF NOT EXISTS idx_batches_product ON inventory_batches(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_batches_expiry ON inventory_batches(expiry_date)",
    "CREATE INDEX IF NOT EXISTS idx_daily_demand_product ON daily_demand(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_forecasts_product_target ON forecasts(product_id, target_date)",
    "CREATE INDEX IF NOT EXISTS idx_reco_status ON reorder_recommendations(status)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_observations_product ON supplier_observations(product_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_source_ref ON sales(source, external_ref) WHERE external_ref IS NOT NULL",
]


# Non-secret default preferences seeded on first initialisation.
DEFAULT_SETTINGS: dict[str, str] = {
    "currency": "INR",
    "shop_name": "",
    "forecast_horizon_days": "7",
    "forecast_baseline_method": "best",
    "service_level": "0.90",
    "safety_policy": "heuristic",
    "review_period_days": "2",
    "safety_buffer_days": "2",
    "near_expiry_window_days": "7",
}


def initialize_database(db: DatabaseConnection) -> None:
    """Create tables, indexes, schema version, and default settings (idempotent)."""
    with db.get_connection() as conn:
        for statement in TABLES:
            conn.execute(statement)
        for statement in INDEXES:
            conn.execute(statement)
        _record_schema_version(conn)
        _seed_default_settings(conn)
    logger.info("Database initialised (schema version %s)", SCHEMA_VERSION)


def _record_schema_version(conn) -> None:
    row = conn.execute("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    elif row["version"] != SCHEMA_VERSION:
        # Forward migrations hook in here in later stages.
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))


def _seed_default_settings(conn) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO NOTHING",
            (key, value),
        )


def get_schema_version(db: DatabaseConnection) -> int | None:
    row = db.query_one("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1")
    return row["version"] if row is not None else None
