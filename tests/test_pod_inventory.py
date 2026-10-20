from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from db import connect, transaction
from pod_schema import apply_pod_schema
from repositories.clients import ClientRepository
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from repositories.products import ProductRepository
from repositories.settings import SettingsRepository
from schema import apply_schema
from services.client_service import ClientService
from services.inventory_service import InventoryService
from services.order_service import OrderService
from services.product_service import ProductService


class InventoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_schema(self.conn)
        self.logs = LogRepository(self.conn)
        self.products = ProductService(self.conn, ProductRepository(self.conn), self.logs)
        self.inventory = InventoryService(self.conn)
        self.clients = ClientService(self.conn, ClientRepository(self.conn), self.logs)
        self.client_id = self.clients.create_client({"nome": "Ana", "email": "ana@example.com"})
        self.orders = OrderService(
            self.conn,
            OrderRepository(self.conn),
            ProductRepository(self.conn),
            ClientRepository(self.conn),
            self.logs,
            SettingsRepository(self.conn),
        )

    def tearDown(self) -> None:
        self.conn.close()

    def product(self, strategy: str = "misto", stock: int = 6, sku: str = "TSHIRT") -> int:
        return self.products.create_product(
            {
                "nome": "T-shirt",
                "sku": sku,
                "preco": "12.34",
                "custo": "5.67",
                "stock": stock,
                "tipo_producao": strategy,
                "technique": "DTF",
            }
        )

    def order(self, product_id: int, quantity: int = 10, **item_extra: object) -> int:
        return self.orders.create_order(
            {
                "client_id": self.client_id,
                "estado": "confirmada",
                "items": [{"product_id": product_id, "quantidade": quantity, **item_extra}],
            }
        )

    def test_mixed_reserves_available_and_produces_only_remainder(self) -> None:
        product_id = self.product()
        order_id = self.order(product_id)
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["stock_on_hand"], product["stock_reserved"], product["stock_available"]), (6, 6, 0))
        tasks = self.inventory.list_tasks(order_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["quantity"], 4)
        self.assertEqual(tasks[0]["technique"], "DTF")
        with transaction(self.conn):
            self.inventory.allocate_order(order_id)
        self.assertEqual(len([m for m in self.inventory.list_movements() if m["kind"] == "reserve"]), 1)

    def test_pod_never_reserves_finished_stock(self) -> None:
        product_id = self.product("print_on_demand", 6)
        order_id = self.order(product_id, 3)
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["stock"], product["stock_reserved"]), (6, 0))
        self.assertEqual(self.inventory.list_tasks(order_id)[0]["quantity"], 3)

    def test_physical_order_can_skip_production(self) -> None:
        product_id = self.product("stock_fisico", 6)
        order_id = self.order(product_id, 3)
        self.assertEqual(self.inventory.list_tasks(order_id), [])
        self.orders.mark_ready(order_id)
        self.assertEqual(self.orders.get_order(order_id)["estado"], "pronta_envio")  # type: ignore[index]

    def test_release_reallocate_same_item_preserves_identity_and_is_idempotent(self) -> None:
        product_id = self.product()
        order_id = self.order(product_id)
        item_id = self.orders.get_order_items(order_id)[0]["id"]
        with transaction(self.conn):
            self.inventory.release_order(order_id)
            self.inventory.release_order(order_id)
            self.inventory.allocate_order(order_id)
        self.assertEqual(self.orders.get_order_items(order_id)[0]["id"], item_id)
        self.orders.cancel_order(order_id)
        movement_count = len(self.inventory.list_movements())
        self.orders.cancel_order(order_id)
        self.assertEqual(len(self.inventory.list_movements()), movement_count)
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["stock_on_hand"], product["stock_reserved"], product["stock"]), (6, 0, 6))

    def test_dispatch_consumes_physical_stock_once(self) -> None:
        product_id = self.product()
        order_id = self.order(product_id)
        self.orders.start_production(order_id)
        self.orders.mark_produced(order_id)
        self.orders.set_payment(order_id, True)
        self.orders.update_tracking(order_id, "PT1234")
        self.orders.dispatch_order(order_id)
        with transaction(self.conn):
            self.inventory.consume_order(order_id)
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["stock_on_hand"], product["stock_reserved"], product["stock"]), (0, 0, 0))
        self.assertEqual(len([m for m in self.inventory.list_movements() if m["kind"] == "dispatch"]), 1)

    def test_rollback_when_a_later_item_has_insufficient_stock(self) -> None:
        first = self.product("stock_fisico", 6)
        second = self.product("stock_fisico", 1, "SECOND")
        with self.assertRaisesRegex(ValueError, "Stock insuficiente"):
            self.orders.create_order(
                {
                    "client_id": self.client_id,
                    "estado": "confirmada",
                    "items": [{"product_id": first, "quantidade": 4}, {"product_id": second, "quantidade": 4}],
                }
            )
        self.assertEqual(self.products.get_product(first)["stock"], 6)  # type: ignore[index]
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM inventory_allocations").fetchone()[0], 0)
        self.assertEqual(self.orders.list_orders(), [])

    def test_variants_have_independent_stock_and_historical_prices(self) -> None:
        product_id = self.product("stock_fisico", 6)
        variant_id = self.products.create_variant(
            product_id,
            {"sku": "TSHIRT-M-BLUE", "tamanho": "M", "cor": "Azul", "preco": "20", "custo": "8", "stock_on_hand": 2},
        )
        order_id = self.order(product_id, 2, variant_id=variant_id)
        item = self.orders.get_order_items(order_id)[0]
        self.assertEqual((item["sku_snapshot"], item["preco_unit_cents"]), ("TSHIRT-M-BLUE", 2000))
        self.products.update_variant(variant_id, {"preco": "25"})
        self.orders.update_order(order_id, {"notas": "Contactar por telefone"})
        self.assertEqual(self.orders.get_order_items(order_id)[0]["preco_unit_cents"], 2000)
        self.assertEqual(self.products.list_variants(product_id)[0]["stock_available"], 6)
        self.assertEqual(self.products.get_product(product_id)["stock"], 6)  # type: ignore[index]

    def test_art_and_qc_must_be_approved(self) -> None:
        product_id = self.product("print_on_demand", 0)
        order_id = self.order(product_id, 1, personalization="Nome: Ana", artwork_path="originals/example.png")
        item_id = int(self.orders.get_order_items(order_id)[0]["id"])
        with self.assertRaisesRegex(ValueError, "arte"):
            self.orders.start_production(order_id)
        self.inventory.approve_art(item_id)
        self.orders.start_production(order_id)
        with self.assertRaisesRegex(ValueError, "qualidade"):
            self.inventory.complete_task(item_id, qc_passed=False)
        with self.assertRaisesRegex(ValueError, "pendentes"):
            self.orders.mark_ready(order_id)
        self.inventory.complete_task(item_id, qc_passed=True)
        self.orders.mark_ready(order_id)
        self.assertEqual(self.inventory.list_tasks(order_id)[0]["status"], "concluida")

    def test_art_change_resets_approval_on_confirmed_order(self) -> None:
        product_id = self.product("print_on_demand", 0)
        order_id = self.order(product_id, 1, personalization="Ana")
        item_id = int(self.orders.get_order_items(order_id)[0]["id"])
        self.inventory.approve_art(item_id)
        self.orders.update_order(
            order_id, {"items": [{"product_id": product_id, "quantidade": 1, "personalization": "Maria"}]}
        )
        task = self.inventory.list_tasks(order_id)[0]
        self.assertEqual(task["art_approved"], 0)

    def test_adjustment_cannot_consume_reserved_stock(self) -> None:
        product_id = self.product("stock_fisico", 6)
        self.order(product_id, 4)
        variant_id = int(self.products.list_variants(product_id)[0]["id"])
        with self.assertRaisesRegex(ValueError, "reservado"):
            self.inventory.adjust_stock(variant_id, -3, "Contagem física")
        self.inventory.adjust_stock(variant_id, 2, "Receção fornecedor")
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["stock_on_hand"], product["stock_reserved"], product["stock"]), (8, 4, 4))
        with self.assertRaisesRegex(ValueError, "motivo"):
            self.inventory.adjust_stock(variant_id, 1, "")

    def test_legacy_deducted_stock_adoption_preserves_available_and_returns_once(self) -> None:
        product_id = self.product("stock_fisico", 10)
        order_id = self.order(product_id, 2)
        with transaction(self.conn):
            self.conn.execute("DELETE FROM inventory_allocations")
            self.conn.execute("DELETE FROM inventory_movements WHERE kind='reserve'")
            self.conn.execute("UPDATE product_variants SET stock_on_hand=8,stock_reserved=0")
            self.conn.execute("UPDATE order_items SET stock_deducted=1")
            apply_pod_schema(self.conn)
        apply_schema(self.conn)
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["stock_on_hand"], product["stock_reserved"], product["stock"]), (10, 2, 8))
        self.orders.cancel_order(order_id)
        self.orders.cancel_order(order_id)
        self.assertEqual(self.products.get_product(product_id)["stock"], 10)  # type: ignore[index]
        self.assertEqual(len([m for m in self.inventory.list_movements() if m["kind"] == "legacy_adoption"]), 1)

    def test_legacy_production_keeps_completed_status(self) -> None:
        product_id = self.product("print_on_demand", 0)
        order_id = self.order(product_id, 2)
        self.orders.start_production(order_id)
        self.orders.mark_produced(order_id)
        with transaction(self.conn):
            self.conn.execute("DELETE FROM production_tasks")
            self.conn.execute("DELETE FROM inventory_allocations")
            apply_pod_schema(self.conn)
        with transaction(self.conn):
            self.inventory.ensure_ready(order_id)
        self.assertEqual(self.inventory.list_tasks(order_id)[0]["status"], "concluida")

    def test_archive_does_not_prevent_fulfilling_existing_order(self) -> None:
        product_id = self.product("print_on_demand", 0)
        order_id = self.order(product_id, 2)
        self.products.archive_product(product_id)
        self.orders.start_production(order_id)
        self.orders.mark_produced(order_id)
        self.orders.set_payment(order_id, True)
        self.orders.update_tracking(order_id, "ARCHIVED")
        self.orders.dispatch_order(order_id)
        self.assertEqual(self.orders.get_order(order_id)["estado"], "expedida")  # type: ignore[index]

    def test_default_variant_archive_keeps_product_available_for_other_variants(self) -> None:
        product_id = self.product("stock_fisico", 0)
        self.products.create_variant(product_id, {"sku": "SECOND", "preco": "15", "stock_on_hand": 2})
        default = self.products.get_default_variant(product_id)
        assert default is not None
        self.products.update_variant(int(default["id"]), {"ativo": 0})
        self.assertEqual(self.products.get_product(product_id)["ativo"], 1)  # type: ignore[index]

    def test_partial_product_update_preserves_stock_and_technique(self) -> None:
        product_id = self.product("stock_fisico", 6)
        self.products.update_product(product_id, {"nome": "Nome corrigido"})
        product = self.products.get_product(product_id)
        assert product is not None
        self.assertEqual((product["nome"], product["stock"], product["technique"]), ("Nome corrigido", 6, "DTF"))

    def test_two_connections_cannot_overreserve(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "inventory.sqlite3"
            source = connect(path)
            apply_schema(source)
            logs = LogRepository(source)
            products = ProductService(source, ProductRepository(source), logs)
            product_id = products.create_product(
                {"nome": "Stock", "sku": "CONCURRENT", "preco": "10", "stock": 10, "tipo_producao": "stock_fisico"}
            )
            client = ClientService(source, ClientRepository(source), logs).create_client(
                {"nome": "Ana", "email": "a@example.com"}
            )
            source.close()
            gate = threading.Barrier(2)
            outcomes: list[str] = []

            def reserve() -> None:
                conn = connect(path)
                service = OrderService(
                    conn,
                    OrderRepository(conn),
                    ProductRepository(conn),
                    ClientRepository(conn),
                    LogRepository(conn),
                    SettingsRepository(conn),
                )
                gate.wait(timeout=5)
                try:
                    service.create_order(
                        {
                            "client_id": client,
                            "estado": "confirmada",
                            "items": [{"product_id": product_id, "quantidade": 7}],
                        }
                    )
                    outcomes.append("reserved")
                except ValueError:
                    outcomes.append("insufficient")
                finally:
                    conn.close()

            threads = [threading.Thread(target=reserve) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertCountEqual(outcomes, ["reserved", "insufficient"])
            check = connect(path)
            self.assertEqual(
                tuple(check.execute("SELECT stock_on_hand,stock_reserved FROM product_variants").fetchone()), (10, 7)
            )
            self.assertEqual(check.execute("SELECT stock FROM products").fetchone()[0], 3)
            check.close()


if __name__ == "__main__":
    unittest.main()
