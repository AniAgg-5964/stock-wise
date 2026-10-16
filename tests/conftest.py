"""Shared pytest fixtures.

Every test gets an isolated temp database and a fully-wired service graph — the
real app-data database is never touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.services.backup_service import BackupService
from application.services.dashboard_service import DashboardService
from application.services.import_export_service import ImportExportService
from application.services.inventory_service import InventoryService
from application.services.product_service import ProductService
from application.services.sales_service import SalesService
from application.services.supplier_service import SupplierService
from repositories.sqlite.audit_repository import SqliteAuditRepository
from repositories.sqlite.connection import DatabaseConnection
from repositories.sqlite.inventory_repository import SqliteInventoryRepository
from repositories.sqlite.product_repository import SqliteProductRepository
from repositories.sqlite.sales_repository import SqliteSalesRepository
from repositories.sqlite.schema import initialize_database
from repositories.sqlite.settings_repository import SqliteSettingsRepository
from repositories.sqlite.supplier_repository import SqliteSupplierRepository


@pytest.fixture
def ctx(tmp_path):
    """A fresh, isolated app context backed by a temp SQLite file."""
    db = DatabaseConnection(tmp_path / "test_stockwise.db")
    initialize_database(db)

    products = SqliteProductRepository(db)
    suppliers = SqliteSupplierRepository(db)
    inventory_repo = SqliteInventoryRepository(db)
    sales_repo = SqliteSalesRepository(db)
    audit = SqliteAuditRepository(db)
    settings = SqliteSettingsRepository(db)

    product_service = ProductService(products, audit)
    supplier_service = SupplierService(suppliers, products, audit)
    inventory_service = InventoryService(db, inventory_repo, products, audit, supplier_service)
    sales_service = SalesService(db, sales_repo, products, inventory_service, audit)
    import_export_service = ImportExportService(
        products, sales_repo, product_service, inventory_service,
        sales_service, supplier_service, audit,
    )

    return SimpleNamespace(
        db=db,
        products=products,
        suppliers=suppliers,
        inventory_repo=inventory_repo,
        sales_repo=sales_repo,
        audit=audit,
        settings=settings,
        product_service=product_service,
        supplier_service=supplier_service,
        inventory_service=inventory_service,
        sales_service=sales_service,
        import_export_service=import_export_service,
        backup_service=BackupService(db),
        dashboard_service=DashboardService(product_service, inventory_service, sales_repo),
    )


@pytest.fixture
def wired_app_context(ctx):
    """Point the shared ``app_context`` singleton at the temp database.

    Used by view-construction tests so real views can read real (empty) data
    without touching the user's live database.
    """
    from app import bootstrap

    for name, value in vars(ctx).items():
        setattr(bootstrap.app_context, name, value)
    bootstrap.app_context.initialized = True
    return bootstrap.app_context
