from __future__ import annotations

from sqlite3 import Connection

from db import transaction
from repositories.logs import LogRepository
from repositories.settings import SettingsRepository
from services.events import ChangeEvents
from utils import now_iso, to_json


class PreferencesService:
    ALLOWED_KEYS = frozenset({"ui.reduce_motion", "ui.compact_sidebar", "backups.retention_days"})

    def __init__(
        self,
        conn: Connection,
        settings: SettingsRepository,
        logs: LogRepository,
        events: ChangeEvents | None = None,
    ) -> None:
        self.conn = conn
        self.settings = settings
        self.logs = logs
        self.events = events

    def get(self, key: str, default: str = "") -> str:
        return self.settings.get(key, default) or default

    def set(self, key: str, value: str) -> None:
        if key not in self.ALLOWED_KEYS:
            raise ValueError("Preferência desconhecida")
        if key.startswith("ui.") and value not in {"0", "1"}:
            raise ValueError("Preferência inválida")
        if key == "backups.retention_days":
            try:
                days = int(value)
            except ValueError as exc:
                raise ValueError("Retenção inválida") from exc
            if not 1 <= days <= 3650:
                raise ValueError("A retenção deve estar entre 1 e 3650 dias")
        with transaction(self.conn):
            self.settings.set(key, value)
            self.logs.create(now_iso(), "settings", key, "update", "Preferência atualizada", to_json({"value": value}))
        if self.events is not None:
            self.events.emit("settings")
