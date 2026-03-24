from __future__ import annotations

import logging
from sqlite3 import Connection, Row

from db import transaction
from repositories.clients import ClientRepository
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from repositories.products import ProductRepository
from repositories.settings import SettingsRepository
from services.order_domain import (
    EDIT_BLOCKED_STATES,
    INITIAL_CREATION_STATES,
    STOCK_DEDUCTION_STATES,
    VALID_STATES,
    ensure_state_transition,
    ensure_tracking_update_allowed,
    validate_paid_for_state,
    validate_tracking_for_state,
)
from services.order_helpers import PROD_MISTO, PROD_STOCK_FISICO, next_order_number, normalize_production_type
from utils import cents_to_money, money_to_cents, now_iso, to_json

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(
        self,
        conn: Connection,
        orders: OrderRepository,
        products: ProductRepository,
        clients: ClientRepository,
        logs: LogRepository,
        settings: SettingsRepository,
    ) -> None:
        self.conn = conn
        self.orders = orders
        self.products = products
        self.clients = clients
        self.logs = logs
        self.settings = settings

    def list_orders(self) -> list[Row]:
        return self.orders.list_all()

    def list_orders_for_client(self, client_id: int) -> list[Row]:
        return self.orders.list_by_client_id(client_id)

    def get_order(self, order_id: int) -> Row | None:
        return self.orders.get_by_id(order_id)

    def get_order_items(self, order_id: int) -> list[Row]:
        return self.orders.list_items(order_id)

    def create_order(self, payload: dict[str, object]) -> int:
        now = now_iso()
        validated = self._validate_order_payload(payload, now=now, is_create=True)
        with transaction(self.conn):
            validated["numero"] = next_order_number(now, self.settings, self.orders)
            order_id = self.orders.create_order(validated)
            processed_items, subtotal_cents = self._process_items(order_id, validated["items"], str(validated["estado"]), now)
            portes_cents = int(validated["portes_cents"])
            total_cents = subtotal_cents + portes_cents
            self.orders.update_order(
                order_id,
                {
                    **validated,
                    "subtotal_cents": subtotal_cents,
                    "portes_cents": portes_cents,
                    "total_cents": total_cents,
                },
            )
            self.logs.create(
                now,
                "orders",
                str(order_id),
                "create",
                "Encomenda criada",
                to_json(
                    {
                        "numero": validated["numero"],
                        "items": processed_items,
                        "subtotal": str(cents_to_money(subtotal_cents)),
                        "portes": str(cents_to_money(portes_cents)),
                        "total": str(cents_to_money(total_cents)),
                    }
                ),
            )
        return order_id

    def update_order(self, order_id: int, payload: dict[str, object]) -> None:
        current = self.orders.get_by_id(order_id)
        if current is None:
            raise ValueError("Encomenda não encontrada")
        current_state = str(current["estado"])
        if current_state in EDIT_BLOCKED_STATES:
            raise ValueError(f"Encomendas em estado '{current_state}' não podem ser editadas")

        now = now_iso()
        validated = self._validate_order_payload(payload, numero=str(current["numero"]), created_at=str(current["created_at"]), now=now, is_create=False)
        ensure_state_transition(current_state, str(validated["estado"]), action="editar")

        with transaction(self.conn):
            old_items = self.orders.list_items(order_id)
            self._restore_items_stock(old_items)
            self.orders.delete_items(order_id)

            processed_items, subtotal_cents = self._process_items(order_id, validated["items"], str(validated["estado"]), now)
            portes_cents = int(validated["portes_cents"])
            total_cents = subtotal_cents + portes_cents
            self.orders.update_order(
                order_id,
                {
                    **validated,
                    "subtotal_cents": subtotal_cents,
                    "portes_cents": portes_cents,
                    "total_cents": total_cents,
                },
            )
            self.logs.create(
                now,
                "orders",
                str(order_id),
                "update",
                "Encomenda atualizada",
                to_json(
                    {
                        "numero": validated["numero"],
                        "items": processed_items,
                        "subtotal": str(cents_to_money(subtotal_cents)),
                        "portes": str(cents_to_money(portes_cents)),
                        "total": str(cents_to_money(total_cents)),
                    }
                ),
            )

    def cancel_order(self, order_id: int) -> None:
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise ValueError("Encomenda não encontrada")
        current_state = str(order["estado"])
        if current_state == "concluida":
            raise ValueError("Encomendas concluídas não podem ser canceladas")
        if current_state != "cancelada":
            ensure_state_transition(current_state, "cancelada", action="cancelar")

        with transaction(self.conn):
            items = self.orders.list_items(order_id)
            now = now_iso()
            restored_any = False
            for item in items:
                if int(item["stock_deducted"]) == 1 and int(item["stock_returned"]) == 0:
                    self.products.increment_stock(int(item["product_id"]), int(item["quantidade"]), now)
                    self.orders.mark_item_returned(int(item["id"]))
                    restored_any = True
            state_changed = False
            if str(order["estado"]) != "cancelada":
                self.orders.update_state(order_id, "cancelada", now)
                state_changed = True
            if state_changed or restored_any:
                self.logs.create(now, "orders", str(order_id), "cancel", "Encomenda cancelada", to_json({}))

    def duplicate_order(self, order_id: int) -> int:
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise ValueError("Encomenda não encontrada")
        items = self.orders.list_items(order_id)
        payload_items = [{"product_id": int(item["product_id"]), "quantidade": int(item["quantidade"])} for item in items]
        new_payload = {
            "client_id": int(order["client_id"]),
            "estado": "rascunho",
            "pago": 0,
            "tracking": "",
            "metodo_pagamento": str(order["metodo_pagamento"]),
            "portes": str(cents_to_money(int(order["portes_cents"]))),
            "data_prevista": str(order["data_prevista"]),
            "notas": str(order["notas"]),
            "items": payload_items,
        }
        new_order_id = self.create_order(new_payload)
        with transaction(self.conn):
            self.logs.create(
                now_iso(),
                "orders",
                str(new_order_id),
                "duplicate",
                f"Duplicada de #{order_id}",
                to_json({"source_order_id": order_id}),
            )
        return new_order_id

    def update_tracking(self, order_id: int, tracking: str) -> None:
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise ValueError("Encomenda não encontrada")
        current_state = str(order["estado"])
        normalized_tracking = ensure_tracking_update_allowed(current_state, tracking)
        previous_tracking = str(order["tracking"] or "")

        with transaction(self.conn):
            now = now_iso()
            self.orders.update_tracking(order_id, normalized_tracking, now)
            self.logs.create(
                now,
                "orders",
                str(order_id),
                "tracking",
                "Tracking atualizado",
                to_json({"state": current_state, "previous_tracking": previous_tracking, "tracking": normalized_tracking}),
            )

    def _validate_order_payload(
        self,
        payload: dict[str, object],
        numero: str | None = None,
        created_at: str | None = None,
        now: str | None = None,
        is_create: bool = False,
    ) -> dict[str, object]:
        client_id = int(payload.get("client_id", 0))
        if self.clients.get_by_id(client_id) is None:
            raise ValueError("Cliente inválido")

        estado = str(payload.get("estado", "rascunho")).lower()
        if estado not in VALID_STATES:
            raise ValueError("Estado inválido")
        if is_create and estado not in INITIAL_CREATION_STATES:
            allowed = ", ".join(sorted(INITIAL_CREATION_STATES))
            raise ValueError(f"Estado inicial inválido. Use um de: {allowed}")

        portes_cents = money_to_cents(payload.get("portes", "0"))
        if portes_cents < 0:
            raise ValueError("Portes inválidos")

        items = payload.get("items")
        normalized_items = self._normalize_items(items)
        if len(normalized_items) == 0:
            raise ValueError("A encomenda precisa de pelo menos 1 item")

        op_time = now or now_iso()
        normalized_tracking = validate_tracking_for_state(estado, str(payload.get("tracking", "")))
        paid_raw = int(payload.get("pago", 0))
        paid = 1 if paid_raw == 1 else 0

        validate_paid_for_state(estado, paid)

        return {
            "numero": numero or "",
            "client_id": client_id,
            "estado": estado,
            "pago": paid,
            "tracking": normalized_tracking,
            "metodo_pagamento": str(payload.get("metodo_pagamento", "")).strip(),
            "subtotal_cents": 0,
            "portes_cents": portes_cents,
            "total_cents": 0,
            "data_prevista": str(payload.get("data_prevista", "")).strip(),
            "notas": str(payload.get("notas", "")).strip(),
            "created_at": str(created_at or op_time),
            "updated_at": op_time,
            "items": normalized_items,
        }

    def _process_items(self, order_id: int, raw_items: list[dict[str, int]], order_state: str, now: str) -> tuple[list[dict[str, object]], int]:
        processed: list[dict[str, object]] = []
        subtotal_cents = 0
        deduct_stock = order_state in STOCK_DEDUCTION_STATES
        for raw in raw_items:
            product_id = int(raw.get("product_id", 0))
            quantidade = int(raw.get("quantidade", 0))
            if quantidade <= 0:
                logger.warning("Invalid quantity in order item: %s", quantidade)
                raise ValueError("Quantidade inválida")

            product = self.products.get_by_id(product_id)
            if product is None:
                logger.warning("Invalid product in order item: %s", product_id)
                raise ValueError("Produto inválido")

            ptype = normalize_production_type(str(product["tipo_producao"]))
            stock = int(product["stock"])
            stock_deducted = 0

            if deduct_stock and ptype == PROD_STOCK_FISICO:
                if stock < quantidade:
                    logger.warning("Insufficient stock for sku=%s required=%s stock=%s", product["sku"], quantidade, stock)
                    raise ValueError(f"Stock insuficiente para {product['sku']}")
                self.products.decrement_stock(product_id, quantidade, now)
                stock_deducted = 1
            elif deduct_stock and ptype == PROD_MISTO:
                if stock >= quantidade:
                    self.products.decrement_stock(product_id, quantidade, now)
                    stock_deducted = 1

            preco_unit_cents = int(product["preco_cents"])
            custo_unit_cents = int(product["custo_cents"])
            item_data = {
                "product_id": product_id,
                "sku_snapshot": str(product["sku"]),
                "nome_snapshot": str(product["nome"]),
                "quantidade": quantidade,
                "preco_unit_cents": preco_unit_cents,
                "custo_unit_cents": custo_unit_cents,
                "tipo_producao_snapshot": ptype,
                "stock_deducted": stock_deducted,
                "stock_returned": 0,
            }
            self.orders.insert_item(order_id, item_data)
            processed.append(item_data)
            subtotal_cents += preco_unit_cents * quantidade

        return processed, subtotal_cents

    def _restore_items_stock(self, items: list[Row]) -> None:
        for item in items:
            if int(item["stock_deducted"]) == 1 and int(item["stock_returned"]) == 0:
                self.products.increment_stock(int(item["product_id"]), int(item["quantidade"]), now_iso())
                self.orders.mark_item_returned(int(item["id"]))

    def _normalize_items(self, raw_items: object) -> list[dict[str, int]]:
        if not isinstance(raw_items, list):
            return []
        merged: dict[int, int] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            product_id = int(item.get("product_id", 0))
            quantidade = int(item.get("quantidade", 0))
            if product_id <= 0 or quantidade <= 0:
                continue
            merged[product_id] = merged.get(product_id, 0) + quantidade
        return [{"product_id": pid, "quantidade": qty} for pid, qty in merged.items()]
