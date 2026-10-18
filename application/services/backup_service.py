"""StockWise — backup service.

Creates timestamped copies of the SQLite database using SQLite's online backup
API (safe while the app is running). Backups live in the per-user data dir.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import Config


class BackupService:
    def __init__(self, db, forecast_service=None) -> None:
        self.db = db
        # Optional: a restore rewrites `daily_demand`, so anything memoised from it
        # has to be dropped or the app keeps forecasting from the old history.
        self.forecast_service = forecast_service

    def create_backup(self) -> Path:
        Config.ensure_directories()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = Config.BACKUP_DIR / f"stockwise-{stamp}.db"
        with self.db.get_connection() as conn:
            dest = sqlite3.connect(str(target))
            try:
                conn.backup(dest)
            finally:
                dest.close()
        return target

    def list_backups(self) -> list[Path]:
        if not Config.BACKUP_DIR.exists():
            return []
        return sorted(Config.BACKUP_DIR.glob("stockwise-*.db"), reverse=True)

    def restore_backup(self, path: Path | str) -> None:
        """Replace the live database with a backup copy (use with care)."""
        source = Path(path)
        if not source.exists():
            from domain.exceptions import NotFoundError

            raise NotFoundError("Backup", source)
        # Flush WAL into the main file, then drop every cached handle. The copy
        # below replaces the database file, and any connection still open would go
        # on answering from its own page cache - so the restore would report
        # success while the app silently kept showing pre-restore data.
        with self.db.get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.close_all()
        shutil.copy2(source, Config.DB_PATH)
        # The replaced database had its own WAL side-files; leaving those behind
        # would let SQLite replay frames belonging to the old data on top of the
        # restored file.
        for suffix in ("-wal", "-shm"):
            Path(f"{Config.DB_PATH}{suffix}").unlink(missing_ok=True)
        # The restored `daily_demand` is a different history, so every memoised
        # demand read is stale now.
        if self.forecast_service is not None:
            self.forecast_service.invalidate_demand_cache()
