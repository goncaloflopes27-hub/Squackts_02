from __future__ import annotations

import hashlib
from sqlite3 import Connection, Row
from typing import Any

from db import transaction
from repositories.clients import ClientRepository
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from repositories.products import ProductRepository
from repositories.settings import SettingsRepository
from repositories.variants import VariantRepository
from services.events import ChangeEvents
from services.inventory_service import InventoryService
from services.order_domain import (
    COMMERCIAL_EDIT_STATES,
    INITIAL_CREATION_STATES,
    STATE_TRANSITIONS,
    TRACKING_ALLOWED_STATES,
    VALID_STATES,
    OrderActions,
    ensure_state_transition,
    ensure_tracking_update_allowed,
    validate_paid_for_state,
    validate_tracking_for_state,
)
from services.order_queries import OrderPage, OrderQuery
from utils import cents_to_money, checked_cents, item_quantity, money_to_cents, now_iso, to_json

PROD_PRINT_ON_DEMAND = "print_on_demand"
PROD_STOCK_FISICO = "stock_fisico"
PROD_MISTO = "misto"


class OrderService:
    """The only writer of order lifecycle, commercial revisions and fulfilment."""

    def __init__(
        self,
        conn: Connection,
        orders: OrderRepository,
        products: ProductRepository,
        clients: ClientRepository,
        logs: LogRepository,
        settings: SettingsRepository,
        events: ChangeEvents | None = None,
    ) -> None:
        self.conn = conn
        self.orders = orders
        self.products = products
        self.clients = clients
        self.logs = logs
        self.settings = settings
        self.variants = VariantRepository(conn)
        self.events = events

    def list_orders(self) -> list[Row]:
        return self.orders.list_all()

    def search_orders(self, query: OrderQuery) -> OrderPage:
        rows, total = self.orders.search_orders(
            search=query.search,
            state=query.state,
            paid=query.paid,
            date_from=query.date_from,
            date_to_exclusive=query.date_to_exclusive,
            client_id=query.client_id,
            limit=query.limit,
            offset=query.offset,
        )
        return OrderPage(rows, total)

    def get_order(self, order_id: int) -> Row | None:
        return self.orders.get_by_id(order_id)

    def get_order_items(self, order_id: int) -> list[Row]:
        return self.orders.list_items(order_id)

    def get_order_history(self, order_id: int) -> list[Row]:
        return self.orders.get_history(order_id)

    def allowed_actions(self, order_id: int) -> OrderActions:
        order = self._require_order(order_id)
        state = str(order["estado"])
        targets = []
        for target in STATE_TRANSITIONS.get(state, set()):
            if target == "expedida" and (not int(order["pago"]) or not str(order["tracking"]).strip()):
                continue
            if target == "pronta_envio" and any(
                str(task["status"]) != "concluida" or not int(task["qc_approved"])
                for task in self._inventory().list_tasks(order_id)
            ):
                continue
            targets.append(target)
        return OrderActions(
            state, tuple(sorted(targets)), state in COMMERCIAL_EDIT_STATES, state in TRACKING_ALLOWED_STATES
        )

    def create_order(self, payload: dict[str, object]) -> int:
        with transaction(self.conn):
            order_id = self._create_order(payload)
        self._publish(inventory_changed=True)
        return order_id

    def _create_order(self, payload: dict[str, object]) -> int:
        request_key = str(payload.get("idempotency_key", "")).strip()
        fingerprint = hashlib.sha256(
            to_json({k: v for k, v in payload.items() if k != "idempotency_key"}).encode()
        ).hexdigest()
        if request_key:
            existing = self.settings.get(f"orders.request.{request_key}")
            if existing:
                existing_id, previous_fingerprint = existing.split(":", 1)
                if previous_fingerprint != fingerprint:
                    raise ValueError("Pedido já utilizado com dados diferentes")
                self._require_order(int(existing_id))
                return int(existing_id)
        now = now_iso()
        data = self._validate_payload(payload, now, is_create=True)
        data["numero"] = self._next_order_number(now)
        order_id = self.orders.create_order(data)
        self._revise_items(order_id, data["items"], allow_new=True)
        self._update_totals(order_id, data)
        if str(data["estado"]) == "confirmada":
            self._inventory().allocate_order(order_id)
        self._record_payment_time(order_id, 0, int(data["pago"]), now)
        self._audit(order_id, "create", "Encomenda criada", {"numero": data["numero"]})
        if request_key:
            self.settings.set(f"orders.request.{request_key}", f"{order_id}:{fingerprint}")

        return order_id

    def update_order(self, order_id: int, payload: dict[str, object]) -> None:
        with transaction(self.conn):
            current = self._require_order(order_id)
            now = now_iso()
            complete = {**dict(current), "portes": str(cents_to_money(int(current["portes_cents"]))), **payload}
            if "items" not in complete:
                complete["items"] = [self._item_request(row) for row in self.orders.list_items(order_id)]
            data = self._validate_payload(complete, now, current=current)
            state = str(current["estado"])
            target = str(data["estado"])
            old_items = self.orders.list_items(order_id)
            changed_items = self._item_signature(data["items"]) != self._item_signature(
                [self._item_request(row) for row in old_items]
            )
            differences = {
                key: {"before": current[key], "after": data[key]}
                for key in (
                    "client_id",
                    "portes_cents",
                    "pago",
                    "tracking",
                    "metodo_pagamento",
                    "data_prevista",
                    "notas",
                )
                if data[key] != current[key]
            }
            commercial_changed = changed_items or "client_id" in differences or "portes_cents" in differences
            if state == "cancelada" and any(key in differences for key in ("pago", "tracking", "metodo_pagamento")):
                raise ValueError("Encomendas canceladas não permitem alterar pagamento ou tracking")
            if target == state and not changed_items and not differences:
                return
            if commercial_changed and state not in COMMERCIAL_EDIT_STATES:
                raise ValueError(f"Encomendas em estado '{state}' não podem ser editadas comercialmente")
            if int(data["client_id"]) != int(current["client_id"]):
                self._validate_active_client(int(data["client_id"]))
            ensure_state_transition(state, target, action="editar")
            if changed_items:
                if state == "confirmada":
                    self._inventory().release_order(order_id)
                self._revise_items(order_id, data["items"], allow_new=True)
                if state == "confirmada":
                    self._inventory().allocate_order(order_id)
            self._update_totals(order_id, {**data, "estado": state})
            self._record_payment_time(order_id, int(current["pago"]), int(data["pago"]), now)
            if target != state:
                self._transition(order_id, target)
            self._audit(
                order_id,
                "update",
                "Encomenda atualizada",
                {
                    "commercial_changed": commercial_changed,
                    "previous_state": state,
                    "state": target,
                    "previous_paid": int(current["pago"]),
                    "paid": int(data["pago"]),
                    "changes": differences,
                    "previous_total_cents": int(current["total_cents"]),
                    "total_cents": int(self._require_order(order_id)["total_cents"]),
                    "previous_items": [dict(row) for row in old_items] if changed_items else [],
                    "items": [dict(row) for row in self.orders.list_items(order_id)] if changed_items else [],
                },
            )
        self._publish(inventory_changed=changed_items or state != target)

    def change_state(self, order_id: int, new_state: str) -> None:
        with transaction(self.conn):
            self._transition(order_id, new_state)
        self._publish(inventory_changed=True)

    def confirm_order(self, order_id: int) -> None:
        self.change_state(order_id, "confirmada")

    def start_production(self, order_id: int) -> None:
        self.change_state(order_id, "em_producao")

    def mark_ready(self, order_id: int) -> None:
        self.change_state(order_id, "pronta_envio")

    def mark_produced(self, order_id: int) -> None:
        with transaction(self.conn):
            current = self._require_order(order_id)
            if str(current["estado"]) == "pronta_envio":
                return
            ensure_state_transition(str(current["estado"]), "pronta_envio", action="produção")
            self._inventory().complete_order_tasks(order_id)
            self._transition(order_id, "pronta_envio")
        self._publish(inventory_changed=True)

    def dispatch_order(self, order_id: int) -> None:
        self.change_state(order_id, "expedida")

    def complete_order(self, order_id: int) -> None:
        self.change_state(order_id, "concluida")

    def cancel_order(self, order_id: int) -> None:
        self.change_state(order_id, "cancelada")

    def record_refund(self, order_id: int) -> None:
        """Record the operator's confirmation of an external full refund."""
        with transaction(self.conn):
            current = self._require_order(order_id)
            if current["estado"] != "cancelada" or current["refund_status"] == "none" or not int(current["pago"]) or int(current["total_cents"]) <= 0:
                raise ValueError("A encomenda não tem um reembolso pendente")
            if current["refund_status"] == "refunded":
                return
            now = now_iso()
            self.orders.update_refund(order_id, "refunded", now, now)
            self._audit(order_id, "refund", "Reembolso integral confirmado pelo operador", {"amount_cents": int(current["total_cents"])})
        self._publish()

    def set_payment(self, order_id: int, paid: bool, method: str | None = None) -> None:
        with transaction(self.conn):
            current = self._require_order(order_id)
            paid_int = int(paid)
            validate_paid_for_state(str(current["estado"]), paid_int)
            if str(current["estado"]) == "cancelada":
                raise ValueError("Encomendas canceladas não permitem alterar o pagamento")
            normalized_method = str(current["metodo_pagamento"]) if method is None else method.strip()
            if int(current["pago"]) == paid_int and normalized_method == str(current["metodo_pagamento"]):
                return
            now = now_iso()
            self.orders.update_payment(order_id, paid_int, normalized_method, now)
            self._record_payment_time(order_id, int(current["pago"]), paid_int, now)
            self._audit(
                order_id, "payment", "Pagamento atualizado", {"previous_paid": int(current["pago"]), "paid": paid_int}
            )
        self._publish()

    def update_notes(self, order_id: int, notes: str) -> None:
        with transaction(self.conn):
            current = self._require_order(order_id)
            normalized = notes.strip()
            if normalized == str(current["notas"]):
                return
            self.orders.update_notes(order_id, normalized, now_iso())
            self._audit(
                order_id, "notes", "Notas atualizadas", {"previous_notes": str(current["notas"]), "notes": normalized}
            )
        self._publish()

    def update_tracking(self, order_id: int, tracking: str) -> None:
        with transaction(self.conn):
            order = self._require_order(order_id)
            normalized = ensure_tracking_update_allowed(str(order["estado"]), tracking)
            if normalized == str(order["tracking"]):
                return
            self.orders.update_tracking(order_id, normalized, now_iso())
            self._audit(
                order_id,
                "tracking",
                "Tracking atualizado",
                {"previous_tracking": str(order["tracking"]), "tracking": normalized},
            )
        self._publish()

    def reprice_draft(self, order_id: int) -> None:
        with transaction(self.conn):
            current = self._require_order(order_id)
            if str(current["estado"]) != "rascunho":
                raise ValueError("Só pode atualizar preços do catálogo em rascunhos")
            before = int(current["total_cents"])
            for item in self.orders.list_items(order_id):
                product = self.products.get_by_id(int(item["product_id"]))
                if product is None:
                    raise ValueError("Produto inválido")
                variant = self.variants.get(int(item["variant_id"]))
                if variant is None:
                    raise ValueError("Variante inválida")
                self.orders.update_item_prices(
                    int(item["id"]), int(variant["preco_cents"]), int(variant["custo_cents"])
                )
            self._update_totals(order_id, dict(current))
            self._audit(
                order_id,
                "reprice",
                "Preços de rascunho atualizados",
                {"previous_total_cents": before, "total_cents": int(self._require_order(order_id)["total_cents"])},
            )
        self._publish()

    def duplicate_order(self, order_id: int) -> int:
        with transaction(self.conn):
            source = self._require_order(order_id)
            items = self.orders.list_items(order_id)
            duplicate = self._create_order(
                {
                    "client_id": int(source["client_id"]),
                    "estado": "rascunho",
                    "pago": 0,
                    "metodo_pagamento": str(source["metodo_pagamento"]),
                    "portes": str(cents_to_money(int(source["portes_cents"]))),
                    "data_prevista": str(source["data_prevista"]),
                    "notas": str(source["notas"]),
                    "items": [self._item_request(item) for item in items],
                }
            )
            self._audit(duplicate, "duplicate", f"Duplicada de #{order_id}", {"source_order_id": order_id})
        self._publish()
        return duplicate

    def _transition(self, order_id: int, target: str) -> None:
        current = self._require_order(order_id)
        state = str(current["estado"])
        if target not in VALID_STATES:
            raise ValueError("Estado inválido")
        ensure_state_transition(state, target, action="alterar estado")
        if state == target:
            return
        validate_paid_for_state(target, int(current["pago"]))
        validate_tracking_for_state(target, str(current["tracking"]))
        if target == "confirmada":
            self._validate_active_client(int(current["client_id"]))
            for item in self.orders.list_items(order_id):
                product = self.products.get_by_id(int(item["product_id"]))
                if product is None or not int(product["ativo"]):
                    raise ValueError("Produto inativo não pode ser confirmado")
            self._inventory().allocate_order(order_id)
        elif target == "em_producao":
            self._inventory().start_order_tasks(order_id)
        elif target == "pronta_envio":
            self._inventory().ensure_ready(order_id)
        elif target == "expedida":
            self._inventory().ensure_ready(order_id)
            self._inventory().consume_order(order_id)
        elif target == "cancelada":
            self._inventory().release_order(order_id)
            if int(current["pago"]) and int(current["total_cents"]) > 0:
                self.orders.update_refund(order_id, "pending", "", now_iso())
        self.orders.update_state(order_id, target, now_iso())
        self._audit(order_id, "state", f"Estado -> {target}", {"previous_state": state, "state": target})

    def _validate_payload(
        self, payload: dict[str, object], now: str, *, is_create: bool = False, current: Row | None = None
    ) -> dict[str, Any]:
        client_id = int(payload.get("client_id", 0))
        if self.clients.get_by_id(client_id) is None:
            raise ValueError("Cliente inválido")
        if is_create:
            self._validate_active_client(client_id)
        state = str(payload.get("estado", "rascunho")).strip().lower()
        paid = int(payload.get("pago", 0))
        if paid not in (0, 1):
            raise ValueError("Pagamento inválido")
        # Accept old callers while keeping 'paga' out of the persisted lifecycle.
        if state == "paga":
            if is_create:
                raise ValueError("Estado inicial inválido. Use um de: confirmada, rascunho")
            if not paid:
                raise ValueError("Estado 'paga' exige encomenda marcada como paga")
            state = "confirmada"
        if state not in VALID_STATES:
            raise ValueError("Estado inválido")
        if is_create and state not in INITIAL_CREATION_STATES:
            raise ValueError("Estado inicial inválido. Use um de: confirmada, rascunho")
        shipping = money_to_cents(payload.get("portes", 0))
        if shipping < 0:
            raise ValueError("Portes inválidos")
        items = self._normalize_items(payload.get("items"))
        if not items:
            raise ValueError("A encomenda precisa de pelo menos 1 item")
        tracking = validate_tracking_for_state(state, str(payload.get("tracking", "")))
        validate_paid_for_state(state, paid)
        return {
            "numero": str(current["numero"]) if current else "",
            "client_id": client_id,
            "estado": state,
            "pago": paid,
            "tracking": tracking,
            "metodo_pagamento": str(payload.get("metodo_pagamento", "")).strip(),
            "subtotal_cents": 0,
            "portes_cents": shipping,
            "total_cents": 0,
            "data_prevista": str(payload.get("data_prevista", "")).strip(),
            "notas": str(payload.get("notas", "")).strip(),
            "created_at": str(current["created_at"]) if current else now,
            "updated_at": now,
            "items": items,
        }

    def _revise_items(self, order_id: int, requested: list[dict[str, Any]], *, allow_new: bool) -> None:
        existing = {self._item_key(dict(row)): row for row in self.orders.list_items(order_id)}
        for requested_item in requested:
            previous = existing.pop(self._item_key(requested_item), None)
            if previous is not None:
                self.orders.update_item(int(previous["id"]), int(requested_item["quantidade"]))
                continue
            if not allow_new:
                raise ValueError("Novas linhas não são permitidas")
            product = self.products.get_by_id(int(requested_item["product_id"]))
            if product is None:
                raise ValueError("Produto inválido")
            if not int(product["ativo"]):
                raise ValueError("Produto inativo não pode ser adicionado")
            variant = self.variants.get(int(requested_item["variant_id"]))
            if variant is None or int(variant["product_id"]) != int(product["id"]):
                raise ValueError("Variante inválida para o produto")
            if not int(variant["ativo"]):
                raise ValueError("Variante inativa não pode ser adicionada")
            label = " / ".join(str(variant[key]) for key in ("tamanho", "cor") if str(variant[key]))
            self.orders.insert_item(
                order_id,
                {
                    **requested_item,
                    "sku_snapshot": str(variant["sku"]),
                    "nome_snapshot": str(product["nome"]) + (f" · {label}" if label else ""),
                    "preco_unit_cents": int(variant["preco_cents"]),
                    "custo_unit_cents": int(variant["custo_cents"]),
                    "technique_snapshot": dict(product).get("technique", ""),
                    "tipo_producao_snapshot": str(product["tipo_producao"]),
                    "stock_deducted": 0,
                    "stock_returned": 0,
                },
            )
        for removed in existing.values():
            self.orders.delete_item(int(removed["id"]))

    def _update_totals(self, order_id: int, data: dict[str, Any]) -> None:
        subtotal = checked_cents(sum(
            int(row["preco_unit_cents"]) * int(row["quantidade"]) for row in self.orders.list_items(order_id)
        ))
        self.orders.update_order(
            order_id,
            {
                **data,
                "subtotal_cents": subtotal,
                "total_cents": checked_cents(subtotal + int(data["portes_cents"])),
                "updated_at": now_iso(),
            },
        )

    def _require_order(self, order_id: int) -> Row:
        row = self.orders.get_by_id(order_id)
        if row is None:
            raise ValueError("Encomenda não encontrada")
        return row

    def _validate_active_client(self, client_id: int) -> None:
        client = self.clients.get_by_id(client_id)
        if client is None or not int(client["ativo"]):
            raise ValueError("Cliente inativo não pode receber novas encomendas")

    def _record_payment_time(self, order_id: int, previous: int, paid: int, now: str) -> None:
        if previous == paid:
            return
        self.orders.update_payment_recorded_at(order_id, now if paid else "")

    def _audit(self, order_id: int, action: str, detail: str, payload: dict[str, Any]) -> None:
        self.logs.create(now_iso(), "orders", str(order_id), action, detail, to_json(payload))

    def _inventory(self) -> InventoryService:
        return InventoryService(self.conn)

    def _publish(self, *, inventory_changed: bool = False) -> None:
        if self.events is not None:
            self.events.emit("orders")
            if inventory_changed:
                self.events.emit("products")
                self.events.emit("production")

    def _next_order_number(self, now: str) -> str:
        year = now[:4]
        key = f"orders.sequence.{year}"
        seq = max(self.settings.get_int(key, default=0), self.orders.get_max_sequence_for_year(year)) + 1
        self.settings.set_int(key, seq)
        return f"ENC-{year}-{seq:04d}"

    @staticmethod
    def _item_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
        return (
            int(item["product_id"]),
            int(item.get("variant_id") or 0),
            str(item.get("personalization", "")),
            str(item.get("artwork_path", "")),
        )

    def _normalize_items(self, raw_items: object) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            raise ValueError("Itens inválidos")
        merged: dict[tuple[int, int, str, str], dict[str, Any]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError("Item inválido")
            product_id, quantity = int(item.get("product_id", 0)), item_quantity(item.get("quantidade", 0))
            if product_id <= 0 or quantity <= 0:
                raise ValueError("Quantidade ou produto inválido")
            normalized = {
                "product_id": product_id,
                "quantidade": quantity,
                "variant_id": int(item.get("variant_id") or 0) or None,
                "personalization": str(item.get("personalization", "")).strip(),
                "artwork_path": str(item.get("artwork_path", "")).strip(),
            }
            if normalized["variant_id"] is None:
                variant = self.variants.get_default(product_id)
                if variant is None:
                    variant = self.variants.ensure_default(product_id)
                normalized["variant_id"] = int(variant["id"])
            key = self._item_key(normalized)
            if key in merged:
                merged[key]["quantidade"] = item_quantity(merged[key]["quantidade"] + quantity)
            else:
                merged[key] = normalized
        return list(merged.values())

    @staticmethod
    def _item_request(row: Row) -> dict[str, Any]:
        data = dict(row)
        return {
            key: data.get(key, "" if key in {"personalization", "artwork_path"} else None)
            for key in ("product_id", "quantidade", "variant_id", "personalization", "artwork_path")
        }

    @classmethod
    def _item_signature(cls, items: list[dict[str, Any]]) -> list[tuple[tuple[int, int, str, str], int]]:
        return sorted((cls._item_key(item), int(item["quantidade"])) for item in items)
