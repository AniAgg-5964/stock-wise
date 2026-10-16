"""StockWise — Application bootstrap.

Wires the shared application state on startup:
1. Create directories
2. Set up logging
3. Initialise the database + schema
4. (Phase 2) Construct repositories and services

The ``app_context`` singleton is created once and shared by the UI.
"""

from __future__ import annotations

import logging

from app.config import Config
from app.logging_config import setup_logging
from repositories.sqlite.connection import DatabaseConnection
from repositories.sqlite.schema import initialize_database

logger = logging.getLogger(__name__)


class AppContext:
    """Holds shared application state (db, repositories, services)."""

    def __init__(self) -> None:
        self.db: DatabaseConnection | None = None
        # Repositories and services are wired in Phase 2.
        self.initialized: bool = False

    def initialize(self) -> None:
        """Run all startup tasks (idempotent)."""
        Config.ensure_directories()
        setup_logging()

        logger.info("%s starting up (env=%s)", Config.APP_NAME, Config.ENV)
        logger.info("Data directory: %s", Config.APP_DATA_DIR)
        logger.info("Database: %s", Config.DB_PATH)

        self.db = DatabaseConnection()
        initialize_database(self.db)

        self.initialized = True
        logger.info("%s ready.", Config.APP_NAME)


# Shared singleton used by the UI layer.
app_context = AppContext()
