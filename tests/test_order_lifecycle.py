from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from db import connect
from repositories.clients import ClientRepository
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from repositories.products import ProductRepository
from repositories.settings import SettingsRepository
from schema import apply_schema
from services.client_service import ClientService
from services.events import ChangeEvents
from services.order_service import OrderService
from services.product_service import ProductService
from services.production_service import ProductionService


def make_orders(conn: sqlite3.Connection) -> OrderService:
    return OrderService(
        conn,
        OrderRepository(conn),
        ProductRepository(conn),
        ClientRepository(conn),
        LogRepository(conn),
        SettingsRepository(conn),
    )


class OrderLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_schema(self.conn)
        self.orders = make_orders(self.conn)
        self.logs = LogRepository(self.conn)
        self.products = ProductService(self.conn, ProductRepository(self.conn), self.logs)
        self.clients = ClientService(self.conn, ClientRepository(self.conn), self.logs)
        self.production = ProductionService(self.conn, OrderRepository(self.conn), self.logs, self.orders)
        self.client_id = self.clients.create_client({"nome": "Cliente", "email": "cliente@example.com"})
        self.product_id = self.products.create_product(
            {
                "nome": "Produto",
                "sku": "FIS-1",
                "preco": "10.10",
                "custo": "3.00",
                "stock": 10,
                "tipo_producao": "stock_fisico",
            }
        )

    def tearDown(self) -> None:
        self.conn.close()

    def payload(self, **overrides: object) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "estado": "confirmada",
            "pago": 0,
            "portes": "0.20",
            "items": [{"product_id": self.product_id, "quantidade": 2}],
            **overrides,
        }

    def ready(self) -> int:
        order_id = self.orders.create_order(self.payload())
        self.orders.mark_ready(order_id)
        return order_id

    def test_every_entry_point_rejects_dispatch_without_payment_and_tracking(self) -> None:
        order_id = self.ready()
        for action in (self.orders.dispatch_order, self.production.mark_ready_to_ship):
            with self.assertRaises(ValueError):
                action(order_id)
        self.orders.set_payment(order_id, True)
        with self.assertRaisesRegex(ValueError, "Tracking é obrigatório"):
            self.production.mark_ready_to_ship(order_id)
        row = self.orders.get_order(order_id)
        assert row is not None
        self.assertEqual(row["estado"], "pronta_envio")
        product = self.products.get_product(self.product_id)
        assert product is not None
        self.assertEqual(int(product["stock_on_hand"]), 10)

    def test_complete_and_repeat_commands_preserve_balances_and_history(self) -> None:
        order_id = self.ready()
        self.orders.set_payment(order_id, True)
        self.orders.update_tracking(order_id, "TRK-1")
        self.orders.dispatch_order(order_id)
        self.orders.dispatch_order(order_id)
        self.orders.complete_order(order_id)
        self.orders.complete_order(order_id)
        product = self.products.get_product(self.product_id)
        assert product is not None
        self.assertEqual(int(product["stock_on_hand"]), 8)
        self.assertEqual(int(product["stock_reserved"]), 0)
        history = self.orders.get_order_history(order_id)
        self.assertEqual(sum('"state":"expedida"' in row["payload_json"] for row in history), 1)
        with self.assertRaises(ValueError):
            self.orders.cancel_order(order_id)
        with self.assertRaises(ValueError):
            self.orders.set_payment(order_id, False)
        self.orders.update_notes(order_id, "Entregue")
        self.orders.update_tracking(order_id, "TRK-CORRIGIDO")

    def test_catalog_change_and_commercial_revision_preserve_line_snapshot(self) -> None:
        order_id = self.orders.create_order(self.payload())
        before = self.orders.get_order_items(order_id)[0]
        product = self.products.get_product(self.product_id)
        assert product is not None
        self.products.update_product(self.product_id, {**dict(product), "preco": "99.99", "custo": "50.00"})
        self.orders.update_order(order_id, {"notas": "Outra nota"})
        self.orders.update_order(order_id, self.payload(items=[{"product_id": self.product_id, "quantidade": 3}]))
        after = self.orders.get_order_items(order_id)[0]
        self.assertEqual(int(after["id"]), int(before["id"]))
        self.assertEqual(int(after["preco_unit_cents"]), 1010)
        self.assertEqual(int(after["custo_unit_cents"]), 300)
        order = self.orders.get_order(order_id)
        assert order is not None
        self.assertEqual(int(order["total_cents"]), 3050)

    def test_explicit_reprice_only_drafts(self) -> None:
        order_id = self.orders.create_order(self.payload(estado="rascunho"))
        item_id = self.orders.get_order_items(order_id)[0]["id"]
        product = self.products.get_product(self.product_id)
        assert product is not None
        self.products.update_product(self.product_id, {**dict(product), "preco": "0.10"})
        self.orders.reprice_draft(order_id)
        self.assertEqual(self.orders.get_order_items(order_id)[0]["id"], item_id)
        order = self.orders.get_order(order_id)
        assert order is not None
        self.assertEqual(order["total_cents"], 40)
        self.orders.confirm_order(order_id)
        with self.assertRaises(ValueError):
            self.orders.reprice_draft(order_id)

    def test_commercial_revision_locked_after_production_notes_allowed(self) -> None:
        order_id = self.orders.create_order(self.payload())
        self.orders.start_production(order_id)
        with self.assertRaisesRegex(ValueError, "não podem ser editadas"):
            self.orders.update_order(
                order_id, self.payload(estado="em_producao", items=[{"product_id": self.product_id, "quantidade": 3}])
            )
        self.orders.update_order(order_id, {"notas": "Nota operacional"})
        self.orders.update_notes(order_id, "Outra nota")
        self.assertEqual(self.orders.get_order_items(order_id)[0]["quantidade"], 2)

    def test_payment_does_not_change_operational_state_and_has_timestamp(self) -> None:
        order_id = self.orders.create_order(self.payload())
        self.orders.set_payment(order_id, True, "Transferência")
        order = self.orders.get_order(order_id)
        assert order is not None
        self.assertEqual(order["estado"], "confirmada")
        self.assertEqual(order["pago"], 1)
        self.assertTrue(order["payment_recorded_at"])
        timestamp = order["payment_recorded_at"]
        self.orders.set_payment(order_id, True)
        self.assertEqual(self.orders.get_order(order_id)["payment_recorded_at"], timestamp)  # type: ignore[index]

    def test_duplicate_create_request_is_idempotent(self) -> None:
        payload = self.payload(idempotency_key="request-1")
        first = self.orders.create_order(payload)
        self.assertEqual(self.orders.create_order(payload), first)
        self.assertEqual(len(self.orders.list_orders()), 1)
        with self.assertRaisesRegex(ValueError, "dados diferentes"):
            self.orders.create_order({**payload, "notas": "different"})

    def test_failed_duplicate_audit_rolls_back_duplicate_and_number(self) -> None:
        order_id = self.orders.create_order(self.payload())
        original = self.orders.logs.create

        def fail_duplicate(timestamp: str, entity: str, entity_id: str, action: str, detail: str, payload: str) -> int:
            if action == "duplicate":
                raise RuntimeError("audit failure")
            return original(timestamp, entity, entity_id, action, detail, payload)

        with patch.object(self.orders.logs, "create", side_effect=fail_duplicate), self.assertRaises(RuntimeError):
            self.orders.duplicate_order(order_id)
        self.assertEqual(len(self.orders.list_orders()), 1)

    def test_inactive_products_and_clients_rejected_for_new_orders(self) -> None:
        self.conn.execute("UPDATE products SET ativo=0 WHERE id=?", (self.product_id,))
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "inativo"):
            self.orders.create_order(self.payload())
        self.conn.execute("UPDATE products SET ativo=1 WHERE id=?", (self.product_id,))
        self.conn.execute("UPDATE clients SET ativo=0 WHERE id=?", (self.client_id,))
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "inativo"):
            self.orders.create_order(self.payload())
        self.assertEqual(len(self.orders.list_orders()), 0)

    def test_confirmation_revalidates_archived_draft_product(self) -> None:
        order_id = self.orders.create_order(self.payload(estado="rascunho"))
        self.conn.execute("UPDATE products SET ativo=0 WHERE id=?", (self.product_id,))
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "inativo"):
            self.orders.confirm_order(order_id)
        self.orders.update_notes(order_id, "Preservar histórico")

    def test_cancel_twice_releases_only_once(self) -> None:
        order_id = self.orders.create_order(self.payload())
        self.orders.cancel_order(order_id)
        self.orders.cancel_order(order_id)
        product = self.products.get_product(self.product_id)
        assert product is not None
        self.assertEqual(int(product["stock_available"]), 10)
        self.assertEqual(int(product["stock_reserved"]), 0)
        self.assertEqual(sum(row["acao"] == "state" for row in self.orders.get_order_history(order_id)), 1)

    def test_cancel_ready_order_keeps_historical_tracking_and_payment(self) -> None:
        order_id = self.ready()
        self.orders.update_tracking(order_id, "TRACKING-ANTES-CANCELAR")
        self.orders.set_payment(order_id, True)
        self.orders.cancel_order(order_id)
        order = self.orders.get_order(order_id)
        assert order is not None
        self.assertEqual(order["estado"], "cancelada")
        self.assertEqual(order["tracking"], "TRACKING-ANTES-CANCELAR")
        self.assertEqual(order["pago"], 1)
        with self.assertRaises(ValueError):
            self.orders.update_order(order_id, {"pago": 0})

    def test_committed_events_never_publish_failed_or_uncommitted_operations(self) -> None:
        events = ChangeEvents()
        observed: list[tuple[str, bool, int]] = []
        events.subscribe(lambda topic: observed.append((topic, self.conn.in_transaction, len(self.orders.list_orders()))))
        self.orders.events = events
        order_id = self.orders.create_order(self.payload())
        self.assertTrue(observed)
        self.assertTrue(all(not in_transaction and count == 1 for _, in_transaction, count in observed))
        observed.clear()
        with self.assertRaises(ValueError):
            self.orders.dispatch_order(order_id)
        self.assertEqual(observed, [])
        self.orders.update_notes(order_id, "Nota persistida")
        self.assertEqual(observed, [("orders", False, 1)])

    def test_archiving_a_reserved_product_does_not_block_fulfilment(self) -> None:
        order_id = self.orders.create_order(self.payload())
        self.conn.execute("UPDATE products SET ativo=0 WHERE id=?", (self.product_id,))
        self.conn.execute("UPDATE product_variants SET ativo=0 WHERE product_id=?", (self.product_id,))
        self.conn.commit()
        self.orders.mark_ready(order_id)
        self.orders.set_payment(order_id, True)
        self.orders.update_tracking(order_id, "TRK-ARQUIVADO")
        self.orders.dispatch_order(order_id)
        self.orders.complete_order(order_id)
        self.assertEqual(self.orders.get_order(order_id)["estado"], "concluida")  # type: ignore[index]

    def test_note_update_has_no_stock_moves_or_duplicate_audit(self) -> None:
        order_id = self.orders.create_order(self.payload())
        movements = self.conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0]
        self.orders.update_order(order_id, {"notas": "Conservar"})
        audit_count = len(self.orders.get_order_history(order_id))
        self.orders.update_order(order_id, {"notas": "Conservar"})
        self.assertEqual(len(self.orders.get_order_history(order_id)), audit_count)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0], movements)

    def test_concurrent_confirmations_do_not_oversell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "orders.sqlite3"
            source = connect(db_path)
            self.conn.backup(source)
            source.close()
            barrier = threading.Barrier(2)
            outcomes: list[str] = []

            def confirm() -> None:
                conn = connect(db_path)
                try:
                    orders = make_orders(conn)
                    barrier.wait(timeout=5)
                    orders.create_order(self.payload(items=[{"product_id": self.product_id, "quantidade": 8}]))
                    outcomes.append("ok")
                except ValueError:
                    outcomes.append("insufficient")
                finally:
                    conn.close()

            threads = [threading.Thread(target=confirm) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
            self.assertCountEqual(outcomes, ["ok", "insufficient"])
            conn = connect(db_path)
            try:
                variant = conn.execute(
                    "SELECT stock_on_hand,stock_reserved FROM product_variants WHERE product_id=?", (self.product_id,)
                ).fetchone()
                self.assertEqual(tuple(variant), (10, 8))
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
