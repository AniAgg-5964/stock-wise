"""StockWise — Application bootstrap.

Wires the shared application state on startup:
1. Create directories
2. Set up logging
3. Initialise the database + schema
4. Construct repositories and services

The ``app_context`` singleton is created once and shared by the UI, which reads
services from it and never touches repositories or SQL directly.

``build_context`` is the single wiring factory; the seed script reuses it.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from app.config import Config
from app.logging_config import setup_logging
from application.services.backup_service import BackupService
from application.services.dashboard_service import DashboardService
from application.services.alert_service import AlertsService
from application.services.forecast_service import ForecastService
from application.services.import_export_service import ImportExportService
from application.services.inventory_service import InventoryService
from application.services.model_service import ModelService
from application.services.product_service import ProductService
from application.services.reorder_service import ReorderService
from application.services.report_service import ReportService
from application.services.sales_service import SalesService
from application.services.supplier_research_service import SupplierResearchService
from application.services.supplier_service import SupplierService
from integrations.tinyfish.client import TinyFishClient
from repositories.sqlite.audit_repository import SqliteAuditRepository
from repositories.sqlite.connection import DatabaseConnection
from repositories.sqlite.forecast_repository import SqliteForecastRepository
from repositories.sqlite.inventory_repository import SqliteInventoryRepository
from repositories.sqlite.product_repository import SqliteProductRepository
from repositories.sqlite.purchase_order_repository import SqlitePurchaseOrderRepository
from repositories.sqlite.reorder_repository import SqliteReorderRepository
from repositories.sqlite.research_repository import (
    SqliteExternalSourceRepository,
    SqliteSupplierObservationRepository,
)
from repositories.sqlite.sales_repository import SqliteSalesRepository
from repositories.sqlite.settings_repository import SqliteSettingsRepository
from repositories.sqlite.supplier_repository import SqliteSupplierRepository

logger = logging.getLogger(__name__)


def build_context(db: DatabaseConnection) -> SimpleNamespace:
    """Construct the full repository + service graph for a database connection."""
    # Repositories
    products = SqliteProductRepository(db)
    suppliers = SqliteSupplierRepository(db)
    inventory_repo = SqliteInventoryRepository(db)
    sales_repo = SqliteSalesRepository(db)
    forecast_repo = SqliteForecastRepository(db)
    purchase_orders = SqlitePurchaseOrderRepository(db)
    reorder_repo = SqliteReorderRepository(db)
    audit = SqliteAuditRepository(db)
    settings = SqliteSettingsRepository(db)

    # Services
    product_service = ProductService(products, audit)
    supplier_service = SupplierService(suppliers, products, audit)
    inventory_service = InventoryService(db, inventory_repo, products, audit, supplier_service)
    sales_service = SalesService(db, sales_repo, products, inventory_service, audit)
    import_export_service = ImportExportService(
        products, sales_repo, product_service, inventory_service,
        sales_service, supplier_service, audit,
    )
    forecast_service = ForecastService(db, forecast_repo, products, settings)
    model_service = ModelService()
    forecast_service.model_service = model_service
    reorder_service = ReorderService(
        db, forecast_service, inventory_service, products, suppliers,
        purchase_orders, reorder_repo, settings, audit,
    )
    alert_service = AlertsService(products, inventory_service, forecast_service, settings)
    report_service = ReportService(
        db, product_service, inventory_service, forecast_service, purchase_orders, products
    )
    # Supplier research is optional: the client does no I/O until a call is made,
    # so an absent API key only disables the feature, never the app.
    external_sources = SqliteExternalSourceRepository(db)
    supplier_observations = SqliteSupplierObservationRepository(db)
    tinyfish_client = TinyFishClient(
        Config.TINYFISH_API_KEY,
        timeout_seconds=Config.TINYFISH_TIMEOUT_SECONDS,
        max_retries=Config.TINYFISH_MAX_RETRIES,
    )
    research_service = SupplierResearchService(
        external_sources, supplier_observations, suppliers, products, audit, settings,
        tinyfish_client,
    )

    return SimpleNamespace(
        db=db,
        products=products,
        suppliers=suppliers,
        inventory_repo=inventory_repo,
        sales_repo=sales_repo,
        forecast_repo=forecast_repo,
        audit=audit,
        settings=settings,
        external_sources=external_sources,
        supplier_observations=supplier_observations,
        product_service=product_service,
        supplier_service=supplier_service,
        inventory_service=inventory_service,
        sales_service=sales_service,
        import_export_service=import_export_service,
        forecast_service=forecast_service,
        model_service=model_service,
        purchase_orders=purchase_orders,
        reorder_repo=reorder_repo,
        reorder_service=reorder_service,
        alert_service=alert_service,
        report_service=report_service,
        tinyfish_client=tinyfish_client,
        research_service=research_service,
        backup_service=BackupService(db),
        dashboard_service=DashboardService(product_service, inventory_service, sales_repo),
    )


class AppContext:
    """Holds shared application state (db, repositories, services)."""

    def __init__(self) -> None:
        self.db: DatabaseConnection | None = None
        self.initialized: bool = False

    def initialize(self) -> None:
        """Run all startup tasks (idempotent)."""
        if self.initialized:
            return

        Config.ensure_directories()
        setup_logging()

        logger.info("%s starting up (env=%s)", Config.APP_NAME, Config.ENV)
        logger.info("Data directory: %s", Config.APP_DATA_DIR)
        logger.info("Database: %s", Config.DB_PATH)

        self.db = DatabaseConnection()
        from repositories.sqlite.schema import initialize_database

        initialize_database(self.db)

        for name, value in vars(build_context(self.db)).items():
            setattr(self, name, value)

        self.initialized = True
        logger.info("%s ready.", Config.APP_NAME)


# Shared singleton used by the UI layer.
app_context = AppContext()
