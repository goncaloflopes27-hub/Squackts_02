from __future__ import annotations

import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from config import SCHEMA_USER_VERSION, AppPaths


def _validated_database(path: Path) -> None:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("A base de dados antiga está corrompida; a origem foi preservada.")
        if int(conn.execute("PRAGMA user_version").fetchone()[0]) > SCHEMA_USER_VERSION:
            raise ValueError("A base de dados antiga requer uma versão mais recente da aplicação.")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("A base de dados antiga tem relações inválidas; a origem foi preservada.")


def migrate_legacy_data(paths: AppPaths) -> bool:
    """Copy a legacy checkout database once, retaining the original and its WAL.

    Existing destination databases always win. Conflicting image files are never
    overwritten. SQLite's backup API captures committed changes still in WAL.
    """
    source = paths.base_dir / "data" / "pod_manager.db"
    if paths.db_path.exists() or not source.is_file() or source.resolve() == paths.db_path.resolve():
        return False
    _validated_database(source)
    old_images = paths.base_dir / "assets" / "images"
    copies: list[tuple[Path, Path]] = []
    for origin, destination in (
        (old_images, paths.images_dir),
        (paths.base_dir / "backups", paths.backups_dir),
        (paths.base_dir / "logs", paths.logs_dir),
    ):
        if origin.is_symlink():
            raise ValueError("A migração não aceita pastas por ligação simbólica.")
        if not origin.is_dir() or origin.resolve() == destination.resolve():
            continue
        for old in sorted(origin.rglob("*")):
            if old.is_symlink():
                raise ValueError("A migração não aceita ligações simbólicas.")
            target = destination / old.relative_to(origin)
            if target.is_symlink():
                raise ValueError("O destino da migração contém uma ligação simbólica.")
            if target.exists():
                if old.is_file() and (not target.is_file() or old.read_bytes() != target.read_bytes()):
                    raise ValueError(f"Ficheiro existente em conflito: {old.relative_to(origin)}")
                if old.is_dir() and not target.is_dir():
                    raise ValueError(f"Pasta existente em conflito: {old.relative_to(origin)}")
            copies.append((old, target))
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".legacy-migration-", dir=paths.db_path.parent) as staging:
        staged_db = Path(staging) / "pod_manager.db"
        with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(staged_db)) as copied:
                original.backup(copied)
        _validated_database(staged_db)
        # Copy assets first: a failed copy leaves no active database or marker.
        for old, target in copies:
            if old.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, target)
        # Only rewrite references whose matching file was actually preserved.
        # External image paths stay untouched rather than inventing a replacement.
        with closing(sqlite3.connect(staged_db)) as copied:
            columns = {row[1] for row in copied.execute("PRAGMA table_info(products)")}
            if "image_path" in columns:
                for product_id, reference in copied.execute(
                    "SELECT id, image_path FROM products WHERE image_path != ''"
                ).fetchall():
                    referenced = Path(reference)
                    candidates = (
                        [referenced]
                        if referenced.is_absolute()
                        else [paths.base_dir / referenced, old_images / referenced]
                    )
                    for candidate in candidates:
                        try:
                            relative = candidate.resolve().relative_to(old_images.resolve())
                        except ValueError:
                            continue
                        if (paths.images_dir / relative).is_file():
                            copied.execute(
                                "UPDATE products SET image_path = ? WHERE id = ?", (relative.as_posix(), product_id)
                            )
                            break
            copied.commit()
        _validated_database(staged_db)
        if paths.db_path.exists():
            raise FileExistsError("O destino foi criado durante a migração; não foi substituído.")
        staged_db.replace(paths.db_path)
    return True
