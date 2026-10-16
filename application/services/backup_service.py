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
    def __init__(self, db) -> None:
        self.db = db

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
        # Flush WAL into the main file before overwriting.
        with self.db.get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(source, Config.DB_PATH)
