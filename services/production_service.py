from __future__ import annotations

from sqlite3 import Connection, Row

from db import transaction
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from services.order_domain import (
    FINAL_STATES,
    ensure_state_transition,
    validate_paid_for_state,
    validate_tracking_for_state,
)
from utils import now_iso, to_json


class ProductionService:
    def __init__(self, conn: Connection, orders: OrderRepository, logs: LogRepository) -> None:
        self.conn = conn
        self.orders = orders
        self.logs = logs

    def get_production_queue(self, status: str | None = None) -> list[Row]:
        return self.orders.get_queue(status)

    def mark_producing(self, order_id: int) -> None:
        self._set_state(order_id, "em_producao", "mark_producing")

    def mark_produced(self, order_id: int) -> None:
        self._set_state(order_id, "pronta_envio", "mark_produced")

    def mark_shipped(self, order_id: int) -> None:
        self._set_state(order_id, "expedida", "mark_shipped")

    def mark_ready_to_ship(self, order_id: int) -> None:
        # Compatibilidade com chamadas antigas; mantém semântica de "expedir".
        self.mark_shipped(order_id)

    def _set_state(self, order_id: int, new_state: str, action: str) -> None:
        current = self.orders.get_by_id(order_id)
        if current is None:
            raise ValueError("Encomenda não encontrada")
        current_state = str(current["estado"])
        if current_state in FINAL_STATES:
            raise ValueError(f"Encomendas em estado '{current_state}' não permitem transições de produção")
        if current_state == new_state:
            raise ValueError(f"Encomenda já está em {new_state}")
        ensure_state_transition(current_state, new_state, action="produção")
        if new_state == "expedida":
            tracking = validate_tracking_for_state(new_state, str(current["tracking"] or ""))
            paid = int(current["pago"])
            validate_paid_for_state(new_state, paid)
            if not tracking:
                raise ValueError("Tracking é obrigatório para expedir")

        with transaction(self.conn):
            now = now_iso()
            self.orders.update_state(order_id, new_state, now)
            self.logs.create(now, "orders", str(order_id), action, f"Estado -> {new_state}", to_json({"state": new_state}))
