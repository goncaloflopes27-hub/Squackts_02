"""Reservation ledger and item-level production rules.

Order operations deliberately leave commits to their caller. Public stock and
checklist commands open a transaction only when none is already in progress.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from sqlite3 import Connection, Row
from typing import Protocol

from db import transaction
from repositories.inventory import InventoryRepository
from repositories.logs import LogRepository
from repositories.production_tasks import ProductionTaskRepository
from repositories.variants import VariantRepository
from utils import now_iso, to_json


class EventSink(Protocol):
    def emit(self, topic: str) -> None: ...


class InventoryService:
    def __init__(self, conn: Connection, events: EventSink | None = None) -> None:
        self.conn = conn
        self.variants = VariantRepository(conn)
        self.inventory = InventoryRepository(conn)
        self.tasks = ProductionTaskRepository(conn)
        self.logs = LogRepository(conn)
        self.events = events

    @contextmanager
    def _write_scope(self) -> Iterator[None]:
        if self.conn.in_transaction:
            yield
        else:
            with transaction(self.conn):
                yield
            if self.events is not None:
                self.events.emit("products")
                self.events.emit("orders")

    def _require_transaction(self) -> None:
        if not self.conn.in_transaction:
            raise RuntimeError("A reserva de stock exige uma transação do serviço de encomendas")

    def allocate_order(self, order_id: int) -> None:
        self._require_transaction()
        now = now_iso()
        for item in self.inventory.list_order_items(order_id):
            if str(item["estado"]) in {"cancelada", "expedida", "concluida"}:
                continue
            item_id, product_id, quantity = int(item["id"]), int(item["product_id"]), int(item["quantidade"])
            variant = (
                self.variants.get(int(item["variant_id"]))
                if item["variant_id"] is not None
                else self.variants.ensure_default(product_id)
            )
            if variant is None or int(variant["product_id"]) != product_id:
                raise ValueError("Variante inválida para o produto")
            current = self.inventory.get_allocation(item_id)
            if current is not None and str(current["status"]) in {"reserved", "consumed"}:
                if int(current["reserved_quantity"]) + int(current["production_quantity"]) != quantity:
                    raise ValueError("Liberte a reserva anterior antes de alterar quantidades")
                self._ensure_task(item, int(current["production_quantity"]), now)
                continue
            if not int(variant["ativo"]):
                raise ValueError("A variante está arquivada")
            strategy = str(item["tipo_producao_snapshot"])
            available = int(variant["stock_available"])
            reserved = 0
            if strategy == "stock_fisico":
                if available < quantity:
                    raise ValueError(f"Stock insuficiente para {variant['sku']}")
                reserved = quantity
            elif strategy == "misto":
                reserved = min(available, quantity)
            production = quantity - reserved
            variant_id = int(variant["id"])
            if reserved and not self.variants.set_balances(variant_id, 0, reserved, now):
                raise ValueError(f"Stock insuficiente para {variant['sku']}")
            self.inventory.save_allocation(item_id, variant_id, reserved, production, now)
            if reserved:
                self.inventory.movement(
                    variant_id, "reserve", 0, reserved, "Reserva ao confirmar encomenda", now, order_id, item_id
                )
            self.variants.sync_product_available(product_id, now)
            self._ensure_task(item, production, now)

    def _ensure_task(self, item: Row, production_quantity: int, now: str) -> None:
        artwork = str(item["artwork_path"] or "").strip()
        personalization = str(item["personalization"] or "").strip()
        reference = (
            to_json({"artwork_path": artwork, "personalization": personalization}) if artwork or personalization else ""
        )
        quantity = production_quantity if production_quantity else (int(item["quantidade"]) if reference else 0)
        if quantity:
            self.tasks.ensure(int(item["id"]), quantity, str(item["technique_snapshot"]), reference, now)
        else:
            self.tasks.remove_for_item(int(item["id"]))

    def release_order(self, order_id: int) -> None:
        self._require_transaction()
        now = now_iso()
        for item in self.inventory.list_order_items(order_id):
            allocation = self.inventory.get_allocation(int(item["id"]))
            if allocation is None or str(allocation["status"]) == "released":
                continue
            reserved = int(allocation["reserved_quantity"])
            variant_id = int(allocation["variant_id"])
            consumed = str(allocation["status"]) == "consumed"
            physical_delta, reserved_delta = (reserved, 0) if consumed else (0, -reserved)
            if reserved:
                if not self.variants.set_balances(variant_id, physical_delta, reserved_delta, now):
                    raise ValueError("Reserva de stock inconsistente; operação anulada")
                self.inventory.movement(
                    variant_id,
                    "return" if consumed else "release",
                    physical_delta,
                    reserved_delta,
                    "Libertação de encomenda",
                    now,
                    order_id,
                    int(item["id"]),
                )
            self.inventory.set_status(int(item["id"]), "released", now)
            self.variants.sync_product_available(int(item["product_id"]), now)

    def consume_order(self, order_id: int) -> None:
        self._require_transaction()
        now = now_iso()
        for item in self.inventory.list_order_items(order_id):
            allocation = self.inventory.get_allocation(int(item["id"]))
            if allocation is None or str(allocation["status"]) == "released":
                raise ValueError("A encomenda não tem reserva de stock válida")
            if str(allocation["status"]) == "consumed":
                continue
            reserved, variant_id = int(allocation["reserved_quantity"]), int(allocation["variant_id"])
            if reserved:
                if not self.variants.set_balances(variant_id, -reserved, -reserved, now):
                    raise ValueError("Reserva de stock inconsistente; operação anulada")
                self.inventory.movement(
                    variant_id,
                    "dispatch",
                    -reserved,
                    -reserved,
                    "Saída de stock por expedição",
                    now,
                    order_id,
                    int(item["id"]),
                )
            self.inventory.set_status(int(item["id"]), "consumed", now)
            self.variants.sync_product_available(int(item["product_id"]), now)

    def list_tasks(self, order_id: int) -> list[Row]:
        return self.tasks.list_for_order(order_id)

    def start_order_tasks(self, order_id: int) -> None:
        self._require_transaction()
        self.allocate_order(order_id)
        pending = self.tasks.list_for_order(order_id)
        if any(int(task["art_required"]) and not int(task["art_approved"]) for task in pending):
            raise ValueError("A arte precisa de aprovação antes de iniciar a produção")
        for task in pending:
            self.start_task(int(task["order_item_id"]))

    def start_task(self, item_id: int) -> None:
        with self._write_scope():
            task = self.tasks.get_for_item(item_id)
            if task is None:
                raise ValueError("Tarefa de produção não encontrada")
            self._ensure_mutable_task(item_id)
            if int(task["art_required"]) and not int(task["art_approved"]):
                raise ValueError("A arte precisa de aprovação antes de iniciar a produção")
            if str(task["status"]) == "pendente":
                self.tasks.start(item_id, now_iso())
                self.logs.create(now_iso(), "order_items", str(item_id), "start_production", "Produção iniciada", "{}")

    def approve_art(self, item_id: int) -> None:
        with self._write_scope():
            task = self.tasks.get_for_item(item_id)
            if task is None:
                raise ValueError("Tarefa de produção não encontrada")
            self._ensure_mutable_task(item_id)
            if int(task["art_approved"]):
                return
            self.tasks.approve_art(item_id, now_iso())
            self.logs.create(now_iso(), "order_items", str(item_id), "approve_art", "Arte aprovada", "{}")

    def complete_task(self, item_id: int, qc_passed: bool = True) -> None:
        with self._write_scope():
            task = self.tasks.get_for_item(item_id)
            if task is None:
                raise ValueError("Tarefa de produção não encontrada")
            self._ensure_mutable_task(item_id)
            if int(task["art_required"]) and not int(task["art_approved"]):
                raise ValueError("A arte precisa de aprovação antes de concluir a produção")
            if int(task["qc_required"]) and not qc_passed:
                raise ValueError("O controlo de qualidade precisa de aprovação")
            if str(task["status"]) == "concluida" and int(task["qc_approved"]):
                return
            self.tasks.complete(item_id, qc_passed, now_iso())
            self.logs.create(
                now_iso(),
                "order_items",
                str(item_id),
                "complete_production",
                "Produção e controlo de qualidade concluídos",
                "{}",
            )

    def _ensure_mutable_task(self, item_id: int) -> None:
        item = self.inventory.get_item(item_id)
        if item is None or str(item["estado"]) not in {"confirmada", "em_producao"}:
            raise ValueError("O estado da encomenda não permite alterar a produção")

    def complete_order_tasks(self, order_id: int) -> None:
        self._require_transaction()
        self.allocate_order(order_id)
        pending = self.tasks.list_for_order(order_id)
        if any(int(task["art_required"]) and not int(task["art_approved"]) for task in pending):
            raise ValueError("A arte precisa de aprovação antes de concluir a produção")
        for task in pending:
            self.complete_task(int(task["order_item_id"]), qc_passed=True)

    def ensure_ready(self, order_id: int) -> None:
        self._require_transaction()
        self.allocate_order(order_id)
        for task in self.tasks.list_for_order(order_id):
            if int(task["art_required"]) and not int(task["art_approved"]):
                raise ValueError("Existe arte por aprovar")
            if str(task["status"]) != "concluida" or (int(task["qc_required"]) and not int(task["qc_approved"])):
                raise ValueError("Existem tarefas de produção ou controlo de qualidade pendentes")

    def list_movements(self, variant_id: int | None = None, limit: int = 200) -> list[Row]:
        return self.inventory.list_movements(variant_id, max(1, min(limit, 1000)))

    def adjust_stock(self, variant_id: int, quantity: int, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Indique o motivo do ajuste de stock")
        with self._write_scope():
            variant = self.variants.get(variant_id)
            if variant is None:
                raise ValueError("Variante não encontrada")
            now = now_iso()
            if not self.variants.set_balances(variant_id, quantity, 0, now):
                raise ValueError("O ajuste não pode consumir stock reservado")
            self.inventory.movement(variant_id, "adjustment", quantity, 0, reason.strip(), now)
            self.variants.sync_product_available(int(variant["product_id"]), now)
            self.logs.create(
                now,
                "product_variants",
                str(variant_id),
                "stock_adjustment",
                reason.strip(),
                to_json({"quantity": quantity}),
            )
