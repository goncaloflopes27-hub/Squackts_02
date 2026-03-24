from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Row

from db import backup_database
from repositories.logs import LogRepository
from repositories.settings import SettingsRepository
from utils import now_iso, to_json

logger = logging.getLogger(__name__)

RETENTION_KEY = "system.backups.retention_count"
DEFAULT_RETENTION = 10
MIN_RETENTION = 1
MAX_RETENTION = 200
EXPECTED_BACKUP_TABLES = {"products", "clients", "orders", "order_items", "logs", "settings"}


@dataclass(slots=True)
class BackupFileInfo:
    path: Path
    size_bytes: int
    modified_at: datetime


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
        settings: SettingsRepository,
        db_path: Path,
        backups_dir: Path,
        images_dir: Path,
        logs_dir: Path,
    ) -> None:
        self.conn = conn
        self.logs = logs
        self.settings = settings
        self.db_path = db_path
        self.backups_dir = backups_dir
        self.images_dir = images_dir
        self.logs_dir = logs_dir

    def create_backup(self) -> Path:
        logger.info("Creating backup to %s", self.backups_dir)
        backup_path = backup_database(self.conn, self.backups_dir)
        removed = self.apply_retention(self.get_retention_count())
        self._log_event(
            "backup_created",
            str(backup_path),
            {"backup_path": str(backup_path), "retention_removed": [str(item) for item in removed]},
        )
        logger.info("Backup created at %s", backup_path)
        return backup_path

    def restore_backup(self, backup_name: str) -> None:
        backup_path = self.backups_dir / backup_name
        if not backup_path.exists() or not backup_path.is_file():
            logger.warning("Backup restore failed: file does not exist (%s)", backup_path)
            raise ValueError("Ficheiro de backup não existe")
        if backup_path.suffix.lower() != ".sqlite3":
            logger.warning("Backup restore failed: invalid extension (%s)", backup_path)
            raise ValueError("Extensão de backup inválida. Esperado .sqlite3")

        logger.info("Validating backup before restore: %s", backup_path)
        self._validate_backup_sqlite(backup_path)

        logger.info("Restoring backup from %s", backup_path)
        try:
            source_conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
            source_conn.row_factory = sqlite3.Row
            source_conn.execute("PRAGMA foreign_keys = ON")
            source_conn.backup(self.conn)
            self.conn.commit()
        except sqlite3.Error as exc:
            logger.exception("Backup restore failed due to sqlite error")
            raise ValueError(f"Restore inválido: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected backup restore failure")
            raise RuntimeError(f"Falha inesperada no restore: {exc}") from exc
        finally:
            if "source_conn" in locals():
                source_conn.close()

        self._log_event("backup_restored", backup_name, {"backup_path": str(backup_path)})
        logger.info("Backup restore complete from %s", backup_path)

    def list_recent_logs(self, limit: int = 12) -> list[Row]:
        return self.logs.list_recent(limit=limit)

    def list_backups(self, limit: int = 12) -> list[BackupFileInfo]:
        if not self.backups_dir.exists():
            return []
        files = [path for path in self.backups_dir.glob("*.sqlite3") if path.is_file()]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        output: list[BackupFileInfo] = []
        for path in files[:limit]:
            stat = path.stat()
            output.append(BackupFileInfo(path=path, size_bytes=stat.st_size, modified_at=datetime.fromtimestamp(stat.st_mtime)))
        return output

    def get_retention_count(self) -> int:
        value = self.settings.get_int(RETENTION_KEY, default=DEFAULT_RETENTION)
        return min(MAX_RETENTION, max(MIN_RETENTION, value))

    def set_retention_count(self, value: int) -> None:
        normalized = min(MAX_RETENTION, max(MIN_RETENTION, int(value)))
        self.settings.set_int(RETENTION_KEY, normalized)
        removed = self.apply_retention(normalized)
        self.conn.commit()
        self._log_event(
            "backup_retention_updated",
            str(normalized),
            {"retention": normalized, "retention_removed": [str(item) for item in removed]},
        )

    def apply_retention(self, retention_count: int) -> list[Path]:
        backups = self.list_backups(limit=10000)
        to_remove = backups[retention_count:]
        removed_paths: list[Path] = []
        for item in to_remove:
            try:
                item.path.unlink(missing_ok=True)
                removed_paths.append(item.path)
            except OSError:
                logger.exception("Failed to remove backup due to retention (%s)", item.path)
        if removed_paths:
            logger.info("Retention removed %d backups", len(removed_paths))
        return removed_paths

    def get_diagnostics(self) -> SystemDiagnostics:
        db_exists = self.db_path.exists()
        db_size_bytes = self.db_path.stat().st_size if db_exists else 0
        user_version_row = self.conn.execute("PRAGMA user_version").fetchone()
        user_version = int(user_version_row[0]) if user_version_row is not None else 0
        connection_ok = False
        try:
            self.conn.execute("SELECT 1").fetchone()
            connection_ok = True
        except sqlite3.Error:
            logger.exception("Connection check failed")
        return SystemDiagnostics(
            db_exists=db_exists,
            db_size_bytes=db_size_bytes,
            db_user_version=user_version,
            connection_ok=connection_ok,
            backups_dir_exists=self.backups_dir.exists(),
            images_dir_exists=self.images_dir.exists(),
            logs_dir_exists=self.logs_dir.exists(),
        )

    def copy_latest_log_file(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.logs_dir / "app.log", destination)
        return destination

    def _validate_backup_sqlite(self, backup_path: Path) -> None:
        try:
            check_conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
            check_conn.row_factory = sqlite3.Row
            integrity_row = check_conn.execute("PRAGMA integrity_check").fetchone()
            integrity_result = str(integrity_row[0]) if integrity_row is not None else ""
            if integrity_result.lower() != "ok":
                logger.warning("Backup integrity_check failed for %s: %s", backup_path, integrity_result)
                raise ValueError("Backup SQLite corrompido (integrity_check falhou)")

            table_rows = check_conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            table_names = {str(row["name"]) for row in table_rows}
            missing = sorted(EXPECTED_BACKUP_TABLES - table_names)
            if missing:
                logger.warning("Backup missing required tables (%s): %s", backup_path, ", ".join(missing))
                raise ValueError(f"Backup incompatível: faltam tabelas obrigatórias ({', '.join(missing)})")
        except ValueError:
            raise
        except sqlite3.Error as exc:
            logger.warning("Backup validation failed for %s: %s", backup_path, exc)
            raise ValueError("Ficheiro .sqlite3 inválido ou não utilizável") from exc
        finally:
            if "check_conn" in locals():
                check_conn.close()

    def _log_event(self, action: str, detail: str, payload: dict[str, object]) -> None:
        self.logs.create(now_iso(), "system", "", action, detail, to_json(payload))
        self.conn.commit()
