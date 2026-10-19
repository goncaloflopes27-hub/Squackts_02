from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from config import DB_PATH, DEFAULT_BUSY_TIMEOUT_MS, SCHEMA_USER_VERSION
from utils import now_iso

Connection = sqlite3.Connection


def connect(db_path: Path = DB_PATH) -> Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_USER_VERSION:
        conn.close()
        raise RuntimeError(f"Base de dados versão {version} mais recente que a aplicação ({SCHEMA_USER_VERSION}).")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def backup_database(source_conn: Connection, backups_dir: Path) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("-", "").replace("+00:00", "Z").replace("T", "_")
    backup_path = backups_dir / f"pod_manager_{stamp}_{uuid4().hex[:8]}.sqlite3"
    backup_conn = sqlite3.connect(backup_path)
    try:
        source_conn.backup(backup_conn)
        backup_conn.commit()
        if backup_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("A cópia de segurança não passou a verificação de integridade.")
    except Exception:
        backup_conn.close()
        backup_path.unlink(missing_ok=True)
        raise
    finally:
        backup_conn.close()
    return backup_path
