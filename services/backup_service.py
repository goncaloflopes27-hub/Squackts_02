from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from sqlite3 import Connection, Row
from typing import Any
from uuid import uuid4

from config import SCHEMA_USER_VERSION
from repositories.logs import LogRepository
from utils import now_iso, to_json

MAX_BACKUP_BYTES = 4 * 1024 * 1024 * 1024
MAX_BACKUP_FILES = 100_000


@dataclass(frozen=True, slots=True)
class BackupInspection:
    format: str
    schema_version: int
    image_count: int
    created_at: str


@dataclass(frozen=True, slots=True)
class RestoreResult:
    restart_required: bool
    recovery_backup: Path


@dataclass(slots=True)
class SystemDiagnostics:
    db_exists: bool
    db_size_bytes: int
    db_user_version: int
    connection_ok: bool
    backups_dir_exists: bool
    images_dir_exists: bool
    logs_dir_exists: bool
    integrity_ok: bool = False
    foreign_keys_ok: bool = False


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_database(path: Path) -> int:
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_USER_VERSION:
                raise ValueError(f"O backup usa a versão {version}; esta aplicação suporta até {SCHEMA_USER_VERSION}.")
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("A base de dados do backup está corrompida.")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("O backup contém relações inválidas.")
            tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"products", "clients", "orders", "order_items"}.issubset(tables):
                raise ValueError("O ficheiro não é uma base de dados Squackts.")
            return version
    except sqlite3.DatabaseError as exc:
        raise ValueError("Não foi possível validar a base de dados do backup.") from exc


class BackupService:
    def __init__(
        self, conn: Connection, logs: LogRepository, db_path: Path, backups_dir: Path, images_dir: Path, logs_dir: Path
    ) -> None:
        self.conn = conn
        self.logs = logs
        self.db_path = db_path
        self.backups_dir = backups_dir
        self.images_dir = images_dir
        self.logs_dir = logs_dir

    def create_backup(self) -> Path:
        if self.conn.in_transaction:
            raise RuntimeError("Termine a operação atual antes de criar um backup.")
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_iso().replace(":", "").replace("-", "")
        backup_path = self.backups_dir / f"squackts_{stamp}_{uuid4().hex[:8]}.zip"
        with tempfile.TemporaryDirectory(prefix=".backup-", dir=self.backups_dir) as work:
            staging = Path(work)
            database = staging / "database.sqlite3"
            with closing(sqlite3.connect(database)) as target:
                self.conn.backup(target)
            version = _check_database(database)
            files: dict[str, dict[str, Any]] = {
                "database.sqlite3": {"sha256": _digest(database), "size": database.stat().st_size}
            }
            # Stage immutable copies so manifest and archived bytes always agree.
            if self.images_dir.exists():
                for image in sorted(self.images_dir.rglob("*")):
                    if image.is_symlink():
                        raise ValueError("O backup não aceita imagens por ligação simbólica.")
                    if not image.is_file():
                        continue
                    relative = PurePosixPath("images", image.relative_to(self.images_dir).as_posix()).as_posix()
                    copied = staging / relative
                    copied.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(image, copied)
                    files[relative] = {"sha256": _digest(copied), "size": copied.stat().st_size}
            manifest = {
                "format": "squackts-backup",
                "format_version": 1,
                "schema_version": version,
                "created_at": now_iso(),
                "database": "database.sqlite3",
                "files": files,
            }
            temporary = staging / "backup.zip"
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                for relative in files:
                    archive.write(staging / relative, relative)
            # Verify the written archive, not just its source data.
            self.inspect_backup(temporary)
            temporary.replace(backup_path)
        self.logs.create(
            now_iso(), "system", "", "backup_created", str(backup_path), to_json({"backup_path": str(backup_path)})
        )
        self.conn.commit()
        return backup_path

    def _stage_backup(self, path: Path, staging: Path) -> BackupInspection:
        if not path.is_file():
            raise ValueError("O ficheiro de backup não existe.")
        if path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("O backup excede o limite de tamanho suportado.")
        if not zipfile.is_zipfile(path):
            database = staging / "database.sqlite3"
            shutil.copy2(path, database)
            version = _check_database(database)
            return BackupInspection("sqlite", version, 0, "")
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_BACKUP_FILES or sum(entry.file_size for entry in entries) > MAX_BACKUP_BYTES:
                    raise ValueError("O conteúdo do backup excede o limite suportado.")
                names: set[str] = set()
                for entry in entries:
                    relative = PurePosixPath(entry.filename)
                    if (
                        relative.is_absolute()
                        or ".." in relative.parts
                        or "\\" in entry.filename
                        or ":" in entry.filename
                        or entry.is_dir()
                        or stat.S_ISLNK(entry.external_attr >> 16)
                        or relative.as_posix() != entry.filename
                        or entry.filename in names
                    ):
                        raise ValueError("O backup contém um caminho inválido ou duplicado.")
                    if not (
                        entry.filename in {"manifest.json", "database.sqlite3"}
                        or (relative.parts and relative.parts[0] == "images" and len(relative.parts) > 1)
                    ):
                        raise ValueError("O backup contém ficheiros inesperados.")
                    names.add(entry.filename)
                if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > 10 * 1024 * 1024:
                    raise ValueError("Manifesto do backup ausente ou inválido.")
                manifest = json.loads(archive.read("manifest.json"))
                if (
                    not isinstance(manifest, dict)
                    or manifest.get("format") != "squackts-backup"
                    or manifest.get("format_version") != 1
                    or manifest.get("database") != "database.sqlite3"
                ):
                    raise ValueError("Formato de manifesto não suportado.")
                files = manifest.get("files")
                if (
                    not isinstance(files, dict)
                    or set(files) != names - {"manifest.json"}
                    or "database.sqlite3" not in files
                ):
                    raise ValueError("O conteúdo do backup não coincide com o manifesto.")
                for relative, expected in files.items():
                    if not isinstance(expected, dict):
                        raise ValueError("Entrada inválida no manifesto do backup.")
                    destination = staging / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(relative) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    if destination.stat().st_size != expected.get("size") or _digest(destination) != expected.get(
                        "sha256"
                    ):
                        raise ValueError(f"Falhou a verificação do ficheiro {relative}.")
                version = _check_database(staging / "database.sqlite3")
                if manifest.get("schema_version") != version:
                    raise ValueError("A versão da base de dados difere do manifesto.")
                return BackupInspection("zip", version, len(files) - 1, str(manifest.get("created_at", "")))
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, UnicodeDecodeError, RuntimeError) as exc:
            raise ValueError("O ficheiro de backup está incompleto, corrompido ou não é suportado.") from exc

    def inspect_backup(self, path: Path | str) -> BackupInspection:
        with tempfile.TemporaryDirectory(prefix="squackts-inspect-") as work:
            return self._stage_backup(Path(path), Path(work))

    def validate_backup(self, path: Path | str) -> BackupInspection:
        return self.inspect_backup(path)

    def restore_backup(self, path: Path | str) -> RestoreResult:
        """Validate and migrate staging, keep a recovery copy, then restore.

        The SQLite backup API updates the existing connection so service references
        remain valid. A restart refreshes all application state after replacement.
        Legacy SQLite-only backups retain the current managed images.
        """
        from schema import apply_schema

        if self.conn.in_transaction:
            raise RuntimeError("Termine a operação atual antes de restaurar dados.")
        self.images_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=self.images_dir.parent) as work:
            staging = Path(work)
            inspection = self._stage_backup(Path(path), staging)
            staged_db = staging / "database.sqlite3"
            with closing(sqlite3.connect(staged_db)) as prepared:
                prepared.execute("PRAGMA foreign_keys = ON")
                apply_schema(prepared)
            _check_database(staged_db)
            recovery = self.create_backup()
            current_db = staging / "recovery.sqlite3"
            with closing(sqlite3.connect(current_db)) as copied:
                self.conn.backup(copied)
            previous_images = staging / "previous-images"
            images_changed = False
            try:
                if inspection.format == "zip":
                    next_images = staging / "images"
                    next_images.mkdir(exist_ok=True)
                    if self.images_dir.exists():
                        self.images_dir.replace(previous_images)
                    try:
                        next_images.replace(self.images_dir)
                    except Exception:
                        if previous_images.exists():
                            previous_images.replace(self.images_dir)
                        raise
                    images_changed = True
                self._replace_database(staged_db)
                if self.conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Falhou a verificação da base de dados restaurada.")
                if self.conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("O restauro produziu relações inválidas.")
            except Exception as failure:
                try:
                    self.conn.rollback()
                    self._replace_database(current_db)
                    if images_changed:
                        shutil.rmtree(self.images_dir)
                        if previous_images.exists():
                            previous_images.replace(self.images_dir)
                except Exception as rollback_error:
                    # Preserve the on-disk recovery package outside temporary staging.
                    raise RuntimeError(
                        f"Recuperação automática incompleta. Use o backup {recovery}."
                    ) from rollback_error
                raise RuntimeError("Restauro cancelado; os dados anteriores foram recuperados.") from failure
        self.logs.create(
            now_iso(), "system", "", "backup_restored", str(path), to_json({"recovery_backup": str(recovery)})
        )
        self.conn.commit()
        return RestoreResult(True, recovery)

    def _replace_database(self, path: Path) -> None:
        with closing(sqlite3.connect(path)) as source:
            source.backup(self.conn)

    def list_recent_logs(self, limit: int = 12) -> list[Row]:
        return self.logs.list_recent(limit=limit)

    def list_backups(self, limit: int = 12) -> list[Path]:
        if not self.backups_dir.exists():
            return []
        files = [
            path
            for path in self.backups_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".zip", ".sqlite3"}
        ]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files[:limit]

    def get_diagnostics(self) -> SystemDiagnostics:
        exists = self.db_path.exists()
        try:
            version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
            integrity = self.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            relations = not self.conn.execute("PRAGMA foreign_key_check").fetchall()
            connection = True
        except sqlite3.DatabaseError:
            version, integrity, relations, connection = 0, False, False, False
        return SystemDiagnostics(
            exists,
            self.db_path.stat().st_size if exists else 0,
            version,
            connection,
            self.backups_dir.exists(),
            self.images_dir.exists(),
            self.logs_dir.exists(),
            integrity,
            relations,
        )
