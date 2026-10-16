"""StockWise — Application configuration and path management.

Owns filesystem locations (per-user app-data dir), environment loading, and
app-wide settings. Mutable data (database, logs, backups, model artifacts)
always lives in a per-user writable directory, never in the repo or CWD.
"""

from __future__ import annotations

import os
import sys
import platform
from pathlib import Path

from dotenv import load_dotenv

# Load `.env` (searched from the current working directory upward) if present.
load_dotenv()


def get_app_data_dir() -> Path:
    """Return the per-user writable application-data directory.

    Windows: %LOCALAPPDATA%\\StockWise
    macOS:   ~/Library/Application Support/StockWise
    Linux:   ~/.local/share/StockWise
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "StockWise"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "StockWise"
    return Path.home() / ".local" / "share" / "StockWise"


def get_project_root() -> Path:
    """Return the project root (the directory containing ``main.py``).

    Resolves correctly both when running from source and when frozen by
    PyInstaller (``sys._MEIPASS``).
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


_APP_DATA_DIR = get_app_data_dir()
_DB_OVERRIDE = os.getenv("STOCKWISE_DB_PATH")


class Config:
    """Central, import-time configuration for the whole application."""

    # --- Environment ---
    ENV: str = os.getenv("STOCKWISE_ENV", "development")
    LOG_LEVEL: str = os.getenv("STOCKWISE_LOG_LEVEL", "INFO")
    DEBUG: bool = ENV == "development"

    # --- Paths ---
    PROJECT_ROOT: Path = get_project_root()
    APP_DATA_DIR: Path = _APP_DATA_DIR
    DB_PATH: Path = Path(_DB_OVERRIDE) if _DB_OVERRIDE else _APP_DATA_DIR / "stockwise.db"
    BACKUP_DIR: Path = _APP_DATA_DIR / "backups"
    LOG_DIR: Path = _APP_DATA_DIR / "logs"
    MODEL_DIR: Path = _APP_DATA_DIR / "models"
    ASSETS_DIR: Path = PROJECT_ROOT / "assets"
    IMPORT_TEMPLATES_DIR: Path = PROJECT_ROOT / "imports" / "templates"
    MIGRATIONS_DIR: Path = PROJECT_ROOT / "migrations"

    # --- Database ---
    DB_SCHEMA_VERSION: int = 1

    # --- Localisation ---
    DEFAULT_CURRENCY: str = "INR"
    CURRENCY_SYMBOL: str = "\u20b9"  # ₹
    CURRENCY_DECIMALS: int = 2

    # --- Forecasting defaults ---
    DEFAULT_FORECAST_HORIZON: int = 7
    MIN_TRAINING_DAYS: int = 14
    BASELINE_LOOKBACK_WEEKS: int = 4

    # --- Inventory / reorder defaults ---
    DEFAULT_SAFETY_BUFFER_DAYS: int = 2
    DEFAULT_REVIEW_PERIOD_DAYS: int = 2
    DEFAULT_LEAD_TIME_DAYS: int = 3
    NEAR_EXPIRY_WINDOW_DAYS: int = 7

    # --- TinyFish (optional supplier research) ---
    TINYFISH_API_KEY: str = os.getenv("TINYFISH_API_KEY", "")
    TINYFISH_TIMEOUT_SECONDS: int = 30
    TINYFISH_MAX_RETRIES: int = 2
    TINYFISH_CACHE_MINUTES: int = 60

    # --- UI ---
    APP_NAME: str = "StockWise"
    APP_TAGLINE: str = "Smarter Stock. Less Waste."
    WINDOW_WIDTH: int = 1366
    WINDOW_HEIGHT: int = 768
    MIN_WINDOW_WIDTH: int = 1024
    MIN_WINDOW_HEIGHT: int = 600

    @classmethod
    def ensure_directories(cls) -> None:
        """Create all required writable directories (idempotent)."""
        for directory in (cls.APP_DATA_DIR, cls.BACKUP_DIR, cls.LOG_DIR, cls.MODEL_DIR):
            directory.mkdir(parents=True, exist_ok=True)
