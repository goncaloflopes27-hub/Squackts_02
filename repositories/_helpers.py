from __future__ import annotations

from sqlite3 import Cursor


def require_lastrowid(cursor: Cursor, entity: str) -> int:
    row_id = cursor.lastrowid
    if row_id is None:
        raise RuntimeError(f"Falha ao obter id gerado para {entity}")
    return int(row_id)
