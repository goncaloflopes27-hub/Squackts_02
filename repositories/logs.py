from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class LogRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, timestamp: str, entidade: str, entidade_id: str, acao: str, detalhe: str, payload_json: str) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO logs (timestamp, entidade, entidade_id, acao, detalhe, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (timestamp, entidade, entidade_id, acao, detalhe, payload_json),
        )
        return require_lastrowid(cursor, "logs")

    def list_recent(self, limit: int = 20) -> list[Row]:
        return self.conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
