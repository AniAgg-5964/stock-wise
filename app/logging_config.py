"""StockWise — Logging configuration.

Structured logging to console + a dated log file. Never logs secrets.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from app.config import Config


def setup_logging() -> None:
    """Configure root logging for the whole application."""
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = Config.LOG_DIR / f"stockwise_{datetime.now():%Y%m%d}.log"

    # Make the console handler tolerant of non-cp1252 characters (e.g. the ₹ symbol).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - platform dependent
        pass

    log_format = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, datefmt=date_format)

    root = logging.getLogger()
    root.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))

    # Avoid stacking handlers if setup runs more than once (e.g. tests, re-init).
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        root.addHandler(console)

    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Suppress noisy third-party loggers.
    for noisy in ("flet", "flet_core", "urllib3", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging initialised (level=%s)", Config.LOG_LEVEL)
