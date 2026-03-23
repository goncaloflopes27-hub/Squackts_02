from __future__ import annotations

import re
from sqlite3 import Connection, Row

from db import transaction
from repositories.clients import ClientRepository
from repositories.logs import LogRepository
from utils import now_iso, to_json


class ClientService:
    EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def __init__(self, conn: Connection, clients: ClientRepository, logs: LogRepository) -> None:
        self.conn = conn
        self.clients = clients
        self.logs = logs

    def list_clients(self) -> list[Row]:
        return self.clients.list_all()

    def create_client(self, payload: dict[str, object]) -> int:
        data = self._validate_payload(payload)
        with transaction(self.conn):
            existing = self.clients.get_by_email(str(data["email"]))
            if existing is not None:
                raise ValueError("Email já existe")
            client_id = self.clients.create(data)
            self.logs.create(now_iso(), "clients", str(client_id), "create", "Cliente criado", to_json(data))
        return client_id

    def update_client(self, client_id: int, payload: dict[str, object]) -> None:
        current = self.clients.get_by_id(client_id)
        if current is None:
            raise ValueError("Cliente não encontrado")
        data = self._validate_payload(payload)
        with transaction(self.conn):
            existing = self.clients.get_by_email(str(data["email"]))
            if existing is not None and int(existing["id"]) != client_id:
                raise ValueError("Email já existe")
            self.clients.update(client_id, data)
            self.logs.create(now_iso(), "clients", str(client_id), "update", "Cliente atualizado", to_json(data))

    def get_client(self, client_id: int) -> Row | None:
        return self.clients.get_by_id(client_id)

    def _validate_payload(self, payload: dict[str, object]) -> dict[str, object]:
        nome = str(payload.get("nome", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        nif = str(payload.get("nif", "")).strip()

        if not nome:
            raise ValueError("Nome é obrigatório")
        if not self.EMAIL_REGEX.match(email):
            raise ValueError("Email inválido")
        if nif and (len(nif) != 9 or not nif.isdigit()):
            raise ValueError("NIF inválido")

        now = now_iso()
        return {
            "nome": nome,
            "email": email,
            "telefone": str(payload.get("telefone", "")).strip(),
            "nif": nif,
            "morada": str(payload.get("morada", "")).strip(),
            "notas": str(payload.get("notas", "")).strip(),
            "ativo": int(payload.get("ativo", 1)),
            "created_at": str(payload.get("created_at", now)),
            "updated_at": now,
        }
