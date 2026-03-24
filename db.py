from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH, DEFAULT_BUSY_TIMEOUT_MS
from utils import now_iso

Connection = sqlite3.Connection


def connect(db_path: Path = DB_PATH) -> Connection:
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
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
    backup_path = backups_dir / f"pod_manager_{stamp}.sqlite3"
    backup_conn = sqlite3.connect(backup_path)
    try:
        source_conn.backup(backup_conn)
        backup_conn.commit()
    finally:
        backup_conn.close()
    return backup_path
