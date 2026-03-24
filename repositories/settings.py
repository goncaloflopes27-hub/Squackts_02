from __future__ import annotations

from sqlite3 import Connection


class SettingsRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row[0])

    def set(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def get_int(self, key: str, default: int = 0) -> int:
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def set_int(self, key: str, value: int) -> None:
        self.set(key, str(value))
