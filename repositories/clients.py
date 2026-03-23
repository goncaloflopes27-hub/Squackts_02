from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class ClientRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def list_all(self) -> list[Row]:
        return self.conn.execute(
            """
            SELECT id, nome, email, telefone, nif, morada, notas, ativo, created_at, updated_at
            FROM clients
            ORDER BY id DESC
            """
        ).fetchall()

    def get_by_id(self, client_id: int) -> Row | None:
        return self.conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()

    def get_by_email(self, email: str) -> Row | None:
        return self.conn.execute("SELECT * FROM clients WHERE lower(email) = lower(?)", (email,)).fetchone()

    def create(self, data: dict[str, object]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO clients (nome, email, telefone, nif, morada, notas, ativo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["nome"],
                data["email"],
                data["telefone"],
                data["nif"],
                data["morada"],
                data["notas"],
                data["ativo"],
                data["created_at"],
                data["updated_at"],
            ),
        )
        return require_lastrowid(cursor, "clients")

    def update(self, client_id: int, data: dict[str, object]) -> None:
        self.conn.execute(
            """
            UPDATE clients
            SET nome = ?, email = ?, telefone = ?, nif = ?, morada = ?, notas = ?, ativo = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["nome"],
                data["email"],
                data["telefone"],
                data["nif"],
                data["morada"],
                data["notas"],
                data["ativo"],
                data["updated_at"],
                client_id,
            ),
        )
