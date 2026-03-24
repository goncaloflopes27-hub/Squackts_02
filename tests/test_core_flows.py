from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from repositories.clients import ClientRepository
from repositories.dashboard import DashboardRepository
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from repositories.products import ProductRepository
from repositories.settings import SettingsRepository
from schema import apply_schema
from services.backup_service import BackupService
from services.client_service import ClientService
from services.dashboard_service import DashboardService
from services.order_helpers import next_order_number
from services.order_service import OrderService
from services.product_service import ProductService
from services.production_service import ProductionService
from utils import configure_logging, money_to_cents


class ServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(self.conn)

        logs_repo = LogRepository(self.conn)
        self.products_repo = ProductRepository(self.conn)
        self.clients_repo = ClientRepository(self.conn)
        self.orders_repo = OrderRepository(self.conn)
        self.settings_repo = SettingsRepository(self.conn)

        self.product_service = ProductService(self.conn, self.products_repo, logs_repo)
        self.client_service = ClientService(self.conn, self.clients_repo, logs_repo)
        self.order_service = OrderService(self.conn, self.orders_repo, self.products_repo, self.clients_repo, logs_repo, self.settings_repo)
        self.production_service = ProductionService(self.conn, self.orders_repo, logs_repo)

        self.client_id = self.client_service.create_client({"nome": "Acme", "email": "acme@example.com", "ativo": 1})
        self.product_stock = self.product_service.create_product(
            {
                "nome": "Camiseta",
                "cor": "Preto",
                "tamanhos": ["M", "G"],
                "descricao": "",
                "preco": "19.99",
                "custo": "7.50",
                "stock": 20,
                "stock_minimo": 2,
                "tipo_producao": "stock_fisico",
                "ativo": 1,
            }
        )
        self.product_pod = self.product_service.create_product(
            {
                "nome": "Poster POD",
                "cor": "Branco",
                "tamanhos": ["TU"],
                "descricao": "",
                "preco": "12.00",
                "custo": "4.00",
                "stock": 0,
                "stock_minimo": 0,
                "tipo_producao": "print_on_demand",
                "ativo": 1,
            }
        )
        self.product_misto = self.product_service.create_product(
            {
                "nome": "Hoodie Misto",
                "cor": "Azul",
                "tamanhos": ["M"],
                "descricao": "",
                "preco": "30.00",
                "custo": "10.00",
                "stock": 2,
                "stock_minimo": 1,
                "tipo_producao": "misto",
                "ativo": 1,
            }
        )

    def tearDown(self) -> None:
        self.conn.close()

    def _order_payload(self, qty: int = 2) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "estado": "confirmada",
            "pago": 0,
            "tracking": "",
            "metodo_pagamento": "manual",
            "portes": "5.20",
            "data_prevista": "",
            "notas": "",
            "items": [{"product_id": self.product_stock, "quantidade": qty}],
        }

    def test_create_order(self) -> None:
        order_id = self.order_service.create_order(self._order_payload())
        order = self.order_service.get_order(order_id)
        self.assertIsNotNone(order)
        assert order is not None
        self.assertEqual(int(order["subtotal_cents"]), 3998)
        self.assertEqual(int(order["portes_cents"]), 520)
        self.assertEqual(int(order["total_cents"]), 4518)

    def test_create_order_rejects_invalid_initial_state(self) -> None:
        payload = self._order_payload(qty=1)
        payload["estado"] = "em_producao"
        with self.assertRaisesRegex(ValueError, "Estado inicial inválido"):
            self.order_service.create_order(payload)

    def test_paid_required_for_paid_state(self) -> None:
        payload = self._order_payload(qty=1)
        payload["estado"] = "confirmada"
        order_id = self.order_service.create_order(payload)
        invalid = self._order_payload(qty=1)
        invalid["estado"] = "paga"
        invalid["pago"] = 0
        with self.assertRaisesRegex(ValueError, "exige encomenda marcada como paga"):
            self.order_service.update_order(order_id, invalid)

    def test_update_order(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.order_service.update_order(order_id, self._order_payload(qty=3))
        order = self.order_service.get_order(order_id)
        assert order is not None
        self.assertEqual(int(order["subtotal_cents"]), 5997)
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 17)

    def test_cancel_order_idempotent(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=2))
        self.order_service.cancel_order(order_id)
        self.order_service.cancel_order(order_id)
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 20)

    def test_duplicate_order(self) -> None:
        payload = self._order_payload(qty=1)
        payload["estado"] = "confirmada"
        payload["pago"] = 0
        payload["tracking"] = ""
        order_id = self.order_service.create_order(payload)
        paid_payload = self._order_payload(qty=1)
        paid_payload["estado"] = "paga"
        paid_payload["pago"] = 1
        self.order_service.update_order(order_id, paid_payload)
        dup_id = self.order_service.duplicate_order(order_id)
        self.assertNotEqual(order_id, dup_id)
        source_items = self.order_service.get_order_items(order_id)
        dup_items = self.order_service.get_order_items(dup_id)
        self.assertEqual(len(source_items), len(dup_items))
        duplicated = self.order_service.get_order(dup_id)
        assert duplicated is not None
        self.assertEqual(str(duplicated["estado"]), "rascunho")
        self.assertEqual(int(duplicated["pago"]), 0)
        self.assertEqual(str(duplicated["tracking"]), "")

    def test_stock_deduction_and_reposition(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=3))
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 17)
        self.order_service.cancel_order(order_id)
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 20)

    def test_stock_rule_print_on_demand(self) -> None:
        payload = self._order_payload(qty=1)
        payload["items"] = [{"product_id": self.product_pod, "quantidade": 5}]
        self.order_service.create_order(payload)
        product = self.product_service.get_product(self.product_pod)
        assert product is not None
        self.assertEqual(int(product["stock"]), 0)

    def test_stock_rule_misto_partial_stock(self) -> None:
        payload = self._order_payload(qty=1)
        payload["items"] = [{"product_id": self.product_misto, "quantidade": 3}]
        self.order_service.create_order(payload)
        product = self.product_service.get_product(self.product_misto)
        assert product is not None
        # stock misto só desconta quando stock >= quantidade; neste caso mantém.
        self.assertEqual(int(product["stock"]), 2)

    def test_stock_rule_misto_deducts_when_enough(self) -> None:
        payload = self._order_payload(qty=1)
        payload["items"] = [{"product_id": self.product_misto, "quantidade": 2}]
        self.order_service.create_order(payload)
        product = self.product_service.get_product(self.product_misto)
        assert product is not None
        self.assertEqual(int(product["stock"]), 0)

    def test_update_order_restores_and_reapplies_stock(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=2))
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 18)
        self.order_service.update_order(order_id, self._order_payload(qty=1))
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 19)

    def test_draft_order_does_not_deduct_stock(self) -> None:
        payload = self._order_payload(qty=2)
        payload["estado"] = "rascunho"
        self.order_service.create_order(payload)
        product = self.product_service.get_product(self.product_stock)
        assert product is not None
        self.assertEqual(int(product["stock"]), 20)

    def test_duplicate_items_are_merged_in_service(self) -> None:
        payload = self._order_payload(qty=1)
        payload["items"] = [
            {"product_id": self.product_stock, "quantidade": 1},
            {"product_id": self.product_stock, "quantidade": 2},
        ]
        order_id = self.order_service.create_order(payload)
        items = self.order_service.get_order_items(order_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(int(items[0]["quantidade"]), 3)

    def test_annual_order_numbering(self) -> None:
        with patch("services.order_service.now_iso", return_value="2026-01-10T10:00:00+00:00"):
            first_id = self.order_service.create_order(self._order_payload(qty=1))
            second_id = self.order_service.create_order(self._order_payload(qty=1))
        first = self.order_service.get_order(first_id)
        second = self.order_service.get_order(second_id)
        assert first is not None and second is not None
        self.assertEqual(str(first["numero"]), "ENC-2026-0001")
        self.assertEqual(str(second["numero"]), "ENC-2026-0002")

    def test_annual_order_numbering_uses_db_max_sequence(self) -> None:
        self.conn.execute(
            """
            INSERT INTO orders
            (numero, client_id, estado, pago, tracking, metodo_pagamento, subtotal_cents, portes_cents, total_cents, data_prevista, notas, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ENC-2026-0042", self.client_id, "rascunho", 0, "", "manual", 0, 0, 0, "", "", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        self.conn.commit()
        with patch("services.order_service.now_iso", return_value="2026-02-01T12:00:00+00:00"):
            new_id = self.order_service.create_order(self._order_payload(qty=1))
        order = self.order_service.get_order(new_id)
        assert order is not None
        self.assertEqual(str(order["numero"]), "ENC-2026-0043")

    def test_annual_order_numbering_not_limited_to_4_digits(self) -> None:
        self.conn.execute(
            """
            INSERT INTO orders
            (numero, client_id, estado, pago, tracking, metodo_pagamento, subtotal_cents, portes_cents, total_cents, data_prevista, notas, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ENC-2026-10000", self.client_id, "rascunho", 0, "", "manual", 0, 0, 0, "", "", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        self.conn.commit()
        with patch("services.order_service.now_iso", return_value="2026-02-15T12:00:00+00:00"):
            new_id = self.order_service.create_order(self._order_payload(qty=1))
        order = self.order_service.get_order(new_id)
        assert order is not None
        self.assertEqual(str(order["numero"]), "ENC-2026-10001")

    def test_update_order_blocked_for_cancelled_or_concluded(self) -> None:
        cancelled_id = self.order_service.create_order(self._order_payload(qty=1))
        self.order_service.cancel_order(cancelled_id)
        with self.assertRaisesRegex(ValueError, "não podem ser editadas"):
            self.order_service.update_order(cancelled_id, self._order_payload(qty=2))

        concluded_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(concluded_id)
        self.production_service.mark_produced(concluded_id)
        ship_payload = self._order_payload(qty=1)
        ship_payload["estado"] = "expedida"
        ship_payload["tracking"] = "TRK-1"
        ship_payload["pago"] = 1
        self.order_service.update_order(concluded_id, ship_payload)
        self.orders_repo.update_state(concluded_id, "concluida", "2026-03-01T00:00:00+00:00")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "não podem ser editadas"):
            self.order_service.update_order(concluded_id, self._order_payload(qty=2))

    def test_update_order_blocked_for_expedida(self) -> None:
        shipped_payload = self._order_payload(qty=1)
        shipped_payload["estado"] = "confirmada"
        order_id = self.order_service.create_order(shipped_payload)
        self.production_service.mark_producing(order_id)
        self.production_service.mark_produced(order_id)
        edit_payload = self._order_payload(qty=1)
        edit_payload["estado"] = "expedida"
        edit_payload["tracking"] = "TRK-EXP-1"
        edit_payload["pago"] = 1
        self.order_service.update_order(order_id, edit_payload)
        with self.assertRaisesRegex(ValueError, "não podem ser editadas"):
            self.order_service.update_order(order_id, self._order_payload(qty=2))

    def test_invalid_state_transition_on_update(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        payload = self._order_payload(qty=1)
        payload["estado"] = "expedida"
        payload["tracking"] = "TRK-SHOULD-FAIL"
        payload["pago"] = 1
        with self.assertRaisesRegex(ValueError, "Transição inválida"):
            self.order_service.update_order(order_id, payload)

    def test_tracking_validation_rules(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        with self.assertRaisesRegex(ValueError, "a partir de pronta_envio"):
            self.order_service.update_tracking(order_id, "   ")

        with self.assertRaisesRegex(ValueError, "a partir de pronta_envio"):
            invalid_payload = self._order_payload(qty=1)
            invalid_payload["tracking"] = "TRK-PREMATURO"
            self.order_service.update_order(order_id, invalid_payload)

    def test_tracking_allowed_from_pronta_envio(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(order_id)
        self.production_service.mark_produced(order_id)
        self.order_service.update_tracking(order_id, "TRK-READY-1")
        order = self.order_service.get_order(order_id)
        assert order is not None
        self.assertEqual(str(order["tracking"]), "TRK-READY-1")

    def test_tracking_required_for_expedida(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(order_id)
        self.production_service.mark_produced(order_id)
        payload = self._order_payload(qty=1)
        payload["estado"] = "expedida"
        payload["tracking"] = ""
        payload["pago"] = 1
        with self.assertRaisesRegex(ValueError, "Tracking é obrigatório"):
            self.order_service.update_order(order_id, payload)

    def test_expedida_requires_paid(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(order_id)
        self.production_service.mark_produced(order_id)
        payload = self._order_payload(qty=1)
        payload["estado"] = "expedida"
        payload["tracking"] = "TRK-EXP-2"
        payload["pago"] = 0
        with self.assertRaisesRegex(ValueError, "exige encomenda marcada como paga"):
            self.order_service.update_order(order_id, payload)

    def test_validations(self) -> None:
        with self.assertRaises(ValueError):
            self.client_service.create_client({"nome": "", "email": "bad", "ativo": 1})
        with self.assertRaises(ValueError):
            self.product_service.create_product(
                {"nome": "", "cor": "", "preco": -1, "custo": 0, "stock": 0, "stock_minimo": 0, "tipo_producao": "x"}
            )
        with self.assertRaises(ValueError):
            self.order_service.create_order({"client_id": 999, "items": []})

    def test_production_invalid_transition(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(order_id)
        with self.assertRaises(ValueError):
            self.production_service.mark_producing(order_id)

    def test_production_blocked_for_final_states(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.order_service.cancel_order(order_id)
        with self.assertRaisesRegex(ValueError, "não permitem transições de produção"):
            self.production_service.mark_producing(order_id)

    def test_production_valid_transition_chain(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(order_id)
        self.production_service.mark_produced(order_id)

        ready_payload = self._order_payload(qty=1)
        ready_payload["estado"] = "pronta_envio"
        ready_payload["tracking"] = "TRK-READY-CHAIN"
        ready_payload["pago"] = 1
        self.order_service.update_order(order_id, ready_payload)

        self.production_service.mark_shipped(order_id)
        order = self.order_service.get_order(order_id)
        assert order is not None
        self.assertEqual(str(order["estado"]), "expedida")

    def test_production_mark_shipped_requires_tracking_and_paid(self) -> None:
        order_id = self.order_service.create_order(self._order_payload(qty=1))
        self.production_service.mark_producing(order_id)
        self.production_service.mark_produced(order_id)
        with self.assertRaisesRegex(ValueError, "Tracking é obrigatório"):
            self.production_service.mark_shipped(order_id)

        ready_payload = self._order_payload(qty=1)
        ready_payload["estado"] = "pronta_envio"
        ready_payload["tracking"] = "TRK-OK-1"
        ready_payload["pago"] = 1
        self.order_service.update_order(order_id, ready_payload)
        self.production_service.mark_shipped(order_id)
        row = self.order_service.get_order(order_id)
        assert row is not None
        self.assertEqual(str(row["estado"]), "expedida")

    def test_validation_product_duplicate_sku(self) -> None:
        created = self.product_service.create_product(
            {
                "nome": "Camiseta",
                "cor": "Preto",
                "descricao": "",
                "preco": "10.00",
                "custo": "1.00",
                "stock": 0,
                "stock_minimo": 0,
                "tipo_producao": "print_on_demand",
                "ativo": 1,
            }
        )
        created_row = self.product_service.get_product(created)
        assert created_row is not None
        self.assertTrue(str(created_row["sku"]).startswith("CAMISETA-PRETO-"))
        self.assertNotEqual(str(created_row["sku"]), "CAMISETA-PRETO")

    def test_product_name_color_are_separate_fields(self) -> None:
        product_id = self.product_service.create_product(
            {
                "nome": "T-Shirt Premium",
                "cor": "Verde floresta",
                "descricao": "teste",
                "preco": "15.50",
                "custo": "5.00",
                "stock": 3,
                "stock_minimo": 1,
                "tipo_producao": "stock_fisico",
                "ativo": 1,
            }
        )
        row = self.product_service.get_product(product_id)
        assert row is not None
        self.assertEqual(str(row["nome"]), "T-Shirt Premium")
        self.assertEqual(str(row["cor"]), "Verde floresta")

    def test_auto_sku_is_deterministic(self) -> None:
        product_id = self.product_service.create_product(
            {
                "nome": "Caneca Premium",
                "cor": "Azul Céu",
                "descricao": "",
                "preco": "8.00",
                "custo": "2.50",
                "stock": 5,
                "stock_minimo": 0,
                "tipo_producao": "misto",
                "ativo": 1,
            }
        )
        row = self.product_service.get_product(product_id)
        assert row is not None
        self.assertEqual(str(row["sku"]), "CANECA-PREMIUM-AZUL-CEU")

    def test_product_sizes_are_persisted(self) -> None:
        product_id = self.product_service.create_product(
            {
                "nome": "Sweatshirt",
                "cor": "Cinza",
                "tamanhos": ["m", "g", "G", " "],
                "descricao": "",
                "preco": "22.00",
                "custo": "11.00",
                "stock": 10,
                "stock_minimo": 2,
                "tipo_producao": "stock_fisico",
                "ativo": 1,
            }
        )
        row = self.product_service.get_product(product_id)
        assert row is not None
        self.assertEqual(str(row["tamanhos_json"]), '["M","G"]')

    def test_validation_client_duplicate_email(self) -> None:
        with self.assertRaises(ValueError):
            self.client_service.create_client({"nome": "Outro", "email": "acme@example.com", "ativo": 1})

    def test_client_email_is_optional(self) -> None:
        client_id = self.client_service.create_client({"nome": "Sem Email", "email": "", "ativo": 1})
        row = self.client_service.get_client(client_id)
        assert row is not None
        self.assertEqual(str(row["email"]), "")

    def test_duplicate_client_names_are_supported_with_unique_ids(self) -> None:
        first_id = self.client_service.create_client({"nome": "Nome Repetido", "email": "", "ativo": 1})
        second_id = self.client_service.create_client({"nome": "Nome Repetido", "email": "", "ativo": 1})
        self.assertNotEqual(first_id, second_id)

        payload = self._order_payload(qty=1)
        payload["client_id"] = second_id
        order_id = self.order_service.create_order(payload)
        order = self.order_service.get_order(order_id)
        assert order is not None
        self.assertEqual(int(order["client_id"]), second_id)

    def test_list_orders_for_client_filters_by_internal_id(self) -> None:
        first_id = self.client_service.create_client({"nome": "Cliente Igual", "email": "igual1@example.com", "ativo": 1})
        second_id = self.client_service.create_client({"nome": "Cliente Igual", "email": "igual2@example.com", "ativo": 1})

        payload_a = self._order_payload(qty=1)
        payload_a["client_id"] = first_id
        self.order_service.create_order(payload_a)

        payload_b = self._order_payload(qty=1)
        payload_b["client_id"] = second_id
        order_b_id = self.order_service.create_order(payload_b)

        rows = self.order_service.list_orders_for_client(second_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["id"]), order_b_id)
        self.assertEqual(int(rows[0]["client_id"]), second_id)

        repo_rows = self.orders_repo.list_by_client_id(second_id)
        self.assertEqual(len(repo_rows), 1)
        self.assertEqual(int(repo_rows[0]["id"]), order_b_id)


class DashboardServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(self.conn)

        logs_repo = LogRepository(self.conn)
        products_repo = ProductRepository(self.conn)
        clients_repo = ClientRepository(self.conn)
        orders_repo = OrderRepository(self.conn)
        settings_repo = SettingsRepository(self.conn)

        self.product_service = ProductService(self.conn, products_repo, logs_repo)
        self.client_service = ClientService(self.conn, clients_repo, logs_repo)
        self.order_service = OrderService(self.conn, orders_repo, products_repo, clients_repo, logs_repo, settings_repo)
        self.dashboard_service = DashboardService(DashboardRepository(self.conn))

        self.client_id = self.client_service.create_client({"nome": "Dash", "email": "dash@example.com", "ativo": 1})
        self.product_id = self.product_service.create_product(
            {
                "nome": "Produto Dash",
                "cor": "Preto",
                "tamanhos": ["M"],
                "descricao": "",
                "preco": "15.50",
                "custo": "5.10",
                "stock": 5,
                "stock_minimo": 5,
                "tipo_producao": "stock_fisico",
                "ativo": 1,
            }
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_summary_without_orders(self) -> None:
        summary = self.dashboard_service.get_summary()
        self.assertEqual(summary.total_orders, 0)
        self.assertEqual(str(summary.total_revenue), "0.00")
        self.assertEqual(str(summary.total_unpaid), "0.00")
        self.assertIn("1 produtos com stock no mínimo", summary.alerts)

    def test_get_summary_with_orders_updates_kpis(self) -> None:
        payload = {
            "client_id": self.client_id,
            "estado": "confirmada",
            "pago": 0,
            "tracking": "",
            "metodo_pagamento": "manual",
            "portes": "2.00",
            "data_prevista": "",
            "notas": "",
            "items": [{"product_id": self.product_id, "quantidade": 2}],
        }
        order_id = self.order_service.create_order(payload)
        self.assertGreater(order_id, 0)

        summary = self.dashboard_service.get_summary()
        self.assertEqual(summary.total_orders, 1)
        self.assertEqual(str(summary.total_revenue), "33.00")
        self.assertEqual(str(summary.total_unpaid), "33.00")
        self.assertEqual(summary.in_production, 1)
        self.assertEqual(summary.production_by_state.get("confirmada"), 1)
        self.assertEqual(len(summary.recent_orders), 1)



class BackupServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "test.sqlite3"
        self.backups_dir = self.root / "backups"
        self.images_dir = self.root / "images"
        self.logs_dir = self.root / "logs"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(self.conn)

        self.logs_repo = LogRepository(self.conn)
        self.settings_repo = SettingsRepository(self.conn)
        self.service = BackupService(
            conn=self.conn,
            logs=self.logs_repo,
            settings=self.settings_repo,
            db_path=self.db_path,
            backups_dir=self.backups_dir,
            images_dir=self.images_dir,
            logs_dir=self.logs_dir,
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp.cleanup()

    def test_retention_is_persisted(self) -> None:
        self.service.set_retention_count(3)
        self.assertEqual(self.service.get_retention_count(), 3)
        self.assertEqual(self.settings_repo.get_int("system.backups.retention_count", default=0), 3)

    def test_create_backup_applies_retention(self) -> None:
        self.service.set_retention_count(2)
        self.service.create_backup()
        self.service.create_backup()
        self.service.create_backup()
        backups = self.service.list_backups(limit=10)
        self.assertEqual(len(backups), 2)

    def test_apply_retention_removes_oldest_backups(self) -> None:
        first = self.service.create_backup()
        second = self.service.create_backup()
        third = self.service.create_backup()
        removed = self.service.apply_retention(2)
        self.assertIn(first, removed)
        self.assertNotIn(second, removed)
        self.assertNotIn(third, removed)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(third.exists())

    def test_restore_invalid_backup_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "não existe"):
            self.service.restore_backup("missing.sqlite3")

    def test_restore_invalid_backup_extension(self) -> None:
        bad = self.backups_dir / "bad.txt"
        bad.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Extensão"):
            self.service.restore_backup("bad.txt")

    def test_restore_rejects_non_sqlite_content(self) -> None:
        fake = self.backups_dir / "fake.sqlite3"
        fake.write_text("not a sqlite db", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inválido"):
            self.service.restore_backup("fake.sqlite3")

    def test_restore_rejects_corrupted_sqlite_file(self) -> None:
        valid = self.backups_dir / "valid.sqlite3"
        conn = sqlite3.connect(valid)
        conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE order_items (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.commit()
        conn.close()

        data = valid.read_bytes()
        valid.write_bytes(data[:64])
        with self.assertRaisesRegex(ValueError, "inválido|corrompido"):
            self.service.restore_backup("valid.sqlite3")

    def test_restore_rejects_missing_required_tables(self) -> None:
        partial = self.backups_dir / "partial.sqlite3"
        conn = sqlite3.connect(partial)
        conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(ValueError, "faltam tabelas obrigatórias"):
            self.service.restore_backup("partial.sqlite3")



class ProductImageFlowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(self.conn)
        logs_repo = LogRepository(self.conn)
        products_repo = ProductRepository(self.conn)
        self.product_service = ProductService(self.conn, products_repo, logs_repo)
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.conn.close()
        self.temp.cleanup()

    def test_prepare_image_asset_creates_png(self) -> None:
        source = Path(self.temp.name) / "sample.jpg"
        image = Image.new("RGB", (128, 128), color=(255, 0, 0))
        image.save(source, format="JPEG")
        result = self.product_service.prepare_image_asset(str(source), "Produto Teste")
        self.assertTrue(Path(result).exists())
        self.assertTrue(result.endswith(".png"))

    def test_prepare_image_asset_avoids_silent_overwrite(self) -> None:
        source = Path(self.temp.name) / "sample_same.jpg"
        image = Image.new("RGB", (128, 128), color=(0, 255, 0))
        image.save(source, format="JPEG")

        first = self.product_service.prepare_image_asset(str(source), "Produto Teste")
        second = self.product_service.prepare_image_asset(str(source), "Produto Teste")

        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).exists())
        self.assertTrue(Path(second).exists())

    def test_prepare_image_asset_rejects_invalid_file(self) -> None:
        source = Path(self.temp.name) / "bad.png"
        source.write_text("not an image", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inválida"):
            self.product_service.prepare_image_asset(str(source), "Produto Teste")


class LoggingSmokeTestCase(unittest.TestCase):
    def test_configure_logging_creates_log_file(self) -> None:
        temp = tempfile.TemporaryDirectory()
        try:
            log_file = Path(temp.name) / "app.log"
            configure_logging(log_file)
            import logging

            logging.getLogger("tests").info("smoke")
            self.assertTrue(log_file.exists())
        finally:
            temp.cleanup()


class OrderHelpersTestCase(unittest.TestCase):
    def test_next_order_number_uses_max_db_sequence(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        logs_repo = LogRepository(conn)
        clients_repo = ClientRepository(conn)
        orders_repo = OrderRepository(conn)
        settings_repo = SettingsRepository(conn)
        client_service = ClientService(conn, clients_repo, logs_repo)
        client_id = client_service.create_client({"nome": "helper", "email": "helper@example.com", "ativo": 1})
        conn.execute(
            """
            INSERT INTO orders
            (numero, client_id, estado, pago, tracking, metodo_pagamento, subtotal_cents, portes_cents, total_cents, data_prevista, notas, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ENC-2026-0020", client_id, "rascunho", 0, "", "manual", 0, 0, 0, "", "", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
        value = next_order_number("2026-03-01T00:00:00+00:00", settings_repo, orders_repo)
        self.assertEqual(value, "ENC-2026-0021")
        conn.close()



class SchemaMigrationTestCase(unittest.TestCase):
    def test_migrate_legacy_real_columns_to_cents(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT NOT NULL UNIQUE, telefone TEXT NOT NULL DEFAULT '', nif TEXT NOT NULL DEFAULT '', morada TEXT NOT NULL DEFAULT '', notas TEXT NOT NULL DEFAULT '', ativo INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL UNIQUE, nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', preco REAL NOT NULL, custo REAL NOT NULL, stock INTEGER NOT NULL DEFAULT 0, stock_minimo INTEGER NOT NULL DEFAULT 0, tipo_producao TEXT NOT NULL, image_path TEXT NOT NULL DEFAULT '', ativo INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT NOT NULL UNIQUE, client_id INTEGER NOT NULL, estado TEXT NOT NULL, pago INTEGER NOT NULL DEFAULT 0, tracking TEXT NOT NULL DEFAULT '', metodo_pagamento TEXT NOT NULL DEFAULT '', subtotal REAL NOT NULL, portes REAL NOT NULL, total REAL NOT NULL, data_prevista TEXT NOT NULL DEFAULT '', notas TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY (client_id) REFERENCES clients(id));
            CREATE TABLE order_items (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, product_id INTEGER NOT NULL, sku_snapshot TEXT NOT NULL, nome_snapshot TEXT NOT NULL, quantidade INTEGER NOT NULL, preco_unit REAL NOT NULL, custo_unit REAL NOT NULL, tipo_producao_snapshot TEXT NOT NULL, stock_deducted INTEGER NOT NULL DEFAULT 0, stock_returned INTEGER NOT NULL DEFAULT 0, FOREIGN KEY (order_id) REFERENCES orders(id), FOREIGN KEY (product_id) REFERENCES products(id));
            INSERT INTO clients (id, nome, email, created_at, updated_at) VALUES (1, 'C', 'c@example.com', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            INSERT INTO products (id, sku, nome, descricao, preco, custo, stock, stock_minimo, tipo_producao, image_path, ativo, created_at, updated_at) VALUES (1, 'S-1', 'P', '', 10.25, 3.10, 4, 1, 'stock_fisico', '', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            INSERT INTO orders (id, numero, client_id, estado, pago, tracking, metodo_pagamento, subtotal, portes, total, data_prevista, notas, created_at, updated_at) VALUES (1, 'ENC-2026-0001', 1, 'pendente', 0, '', 'manual', 10.25, 2.00, 12.25, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            INSERT INTO order_items (order_id, product_id, sku_snapshot, nome_snapshot, quantidade, preco_unit, custo_unit, tipo_producao_snapshot, stock_deducted, stock_returned) VALUES (1, 1, 'S-1', 'P', 1, 10.25, 3.10, 'stock_fisico', 0, 0);
            """
        )

        apply_schema(conn)

        product = conn.execute("SELECT preco_cents, custo_cents, cor, tamanhos_json FROM products WHERE id = 1").fetchone()
        order = conn.execute("SELECT subtotal_cents, portes_cents, total_cents, estado FROM orders WHERE id = 1").fetchone()
        item = conn.execute("SELECT preco_unit_cents, custo_unit_cents FROM order_items WHERE order_id = 1").fetchone()
        self.assertEqual(int(product["preco_cents"]), 1025)
        self.assertEqual(int(product["custo_cents"]), 310)
        self.assertEqual(str(product["cor"]), "")
        self.assertEqual(str(product["tamanhos_json"]), "[]")
        self.assertEqual(int(order["subtotal_cents"]), 1025)
        self.assertEqual(int(order["portes_cents"]), 200)
        self.assertEqual(int(order["total_cents"]), 1225)
        self.assertEqual(str(order["estado"]), "confirmada")
        self.assertEqual(int(item["preco_unit_cents"]), 1025)
        self.assertEqual(int(item["custo_unit_cents"]), 310)

        conn.close()

    def test_apply_schema_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        apply_schema(conn)
        fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(fk, 1)
        self.assertEqual(violations, [])
        conn.close()


class MoneyConversionTestCase(unittest.TestCase):
    def test_half_up_rounding_to_cents(self) -> None:
        self.assertEqual(money_to_cents("10.235"), 1024)
        self.assertEqual(money_to_cents("10.234"), 1023)


if __name__ == "__main__":
    unittest.main()
