from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection, Row

from db import backup_database
from repositories.logs import LogRepository
from utils import now_iso, to_json


@dataclass(slots=True)
class SystemDiagnostics:
    db_exists: bool
    db_size_bytes: int
    db_user_version: int
    connection_ok: bool
    backups_dir_exists: bool
    images_dir_exists: bool
    logs_dir_exists: bool


class BackupService:
    def __init__(
        self,
        conn: Connection,
        logs: LogRepository,
        db_path: Path,
        backups_dir: Path,
        images_dir: Path,
        logs_dir: Path,
    ) -> None:
        self.conn = conn
        self.logs = logs
        self.db_path = db_path
        self.backups_dir = backups_dir
        self.images_dir = images_dir
        self.logs_dir = logs_dir

    def create_backup(self) -> Path:
        backup_path = backup_database(self.conn, self.backups_dir)
        self.logs.create(
            now_iso(),
            "system",
            "",
            "backup_created",
            str(backup_path),
            to_json({"backup_path": str(backup_path)}),
        )
        self.conn.commit()
        return backup_path

    def list_recent_logs(self, limit: int = 12) -> list[Row]:
        return self.logs.list_recent(limit=limit)

    def list_backups(self, limit: int = 12) -> list[Path]:
        if not self.backups_dir.exists():
            return []
        files = [path for path in self.backups_dir.glob("*.sqlite3") if path.is_file()]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files[:limit]

    def get_diagnostics(self) -> SystemDiagnostics:
        db_exists = self.db_path.exists()
        db_size_bytes = self.db_path.stat().st_size if db_exists else 0
        user_version_row = self.conn.execute("PRAGMA user_version").fetchone()
        user_version = int(user_version_row[0]) if user_version_row is not None else 0
        return SystemDiagnostics(
            db_exists=db_exists,
            db_size_bytes=db_size_bytes,
            db_user_version=user_version,
            connection_ok=True,
            backups_dir_exists=self.backups_dir.exists(),
            images_dir_exists=self.images_dir.exists(),
            logs_dir_exists=self.logs_dir.exists(),
        )
