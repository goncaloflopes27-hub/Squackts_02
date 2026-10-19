from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config import AppPaths
from service_container import bootstrap_infrastructure
from services.order_queries import OrderQuery
from utils import format_currency, money_to_cents


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.container = bootstrap_infrastructure(AppPaths.from_home(Path(self.directory.name)), migrate_legacy=False)
        self.client = self.container.clients.create_client({"nome": "Reporting", "email": "report@example.test"})
        self.product = self.container.products.create_product({
            "nome": "Impressão", "sku": "REPORT", "preco": "10.00",
            "custo": "4.00", "tipo_producao": "print_on_demand", "stock": 0,
        })

    def tearDown(self) -> None:
        self.container.close()
        self.directory.cleanup()

    def order(self, state: str, paid: int = 0, quantity: int = 1) -> int:
        return self.container.orders.create_order({
            "client_id": self.client, "estado": state, "pago": paid,
            "items": [{"product_id": self.product, "quantidade": quantity}],
        })

    def test_drafts_and_cancelled_orders_are_not_sales_or_receivables(self) -> None:
        self.order("rascunho", quantity=3)
        self.order("confirmada", paid=1, quantity=2)
        self.order("confirmada", quantity=1)
        cancelled = self.order("confirmada", quantity=4)
        self.container.orders.cancel_order(cancelled)
        summary = self.container.dashboard.get_summary()
        self.assertEqual(summary.total_orders, 4)
        self.assertEqual(summary.total_revenue, 30)
        self.assertEqual(summary.total_paid, 20)
        self.assertEqual(summary.total_unpaid, 10)
        self.assertEqual(summary.pending_confirmation, 1)
        self.assertEqual(summary.production_units, 3)
        self.assertEqual(summary.estimated_margin, 18)
        self.assertEqual(summary.low_stock_count, 0)

    def test_mixed_production_metric_counts_only_unfulfilled_remainder(self) -> None:
        product = self.container.products.create_product({
            "nome": "Misto", "sku": "MIXREPORT", "preco": "10", "custo": "4",
            "tipo_producao": "misto", "stock": 6,
        })
        self.container.orders.create_order({
            "client_id": self.client, "estado": "confirmada",
            "items": [{"product_id": product, "quantidade": 10}],
        })
        self.assertEqual(self.container.dashboard.get_summary().production_units, 4)

    def test_preferences_persist_and_publish_after_commit(self) -> None:
        preferences = self.container.preferences
        assert preferences is not None
        notifications = []
        unsubscribe = self.container.events.subscribe(lambda topic: notifications.append((topic, self.container.conn.in_transaction)))
        preferences.set("ui.reduce_motion", "1")
        self.assertEqual(preferences.get("ui.reduce_motion"), "1")
        self.assertEqual(notifications, [("settings", False)])
        with self.assertRaises(ValueError):
            preferences.set("ui.reduce_motion", "invalid")
        self.assertEqual(preferences.get("ui.reduce_motion"), "1")
        unsubscribe()

    def test_archive_client_preserves_existing_history_and_blocks_new_orders(self) -> None:
        existing = self.order("confirmada")
        self.container.clients.archive_client(self.client)
        self.assertIsNotNone(self.container.orders.get_order(existing))
        with self.assertRaises(ValueError):
            self.order("rascunho")

    def test_money_is_finite_exact_and_formatted_in_portuguese(self) -> None:
        self.assertEqual(money_to_cents("0.10") + money_to_cents("0.20"), 30)
        self.assertEqual(format_currency("1234.56"), "1 234,56 €")
        for value in ("NaN", "Infinity", "-Infinity", "1e100"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money_to_cents(value)

    def test_paginated_search_handles_portuguese_case_and_item_text(self) -> None:
        self.container.clients.update_client(self.client, {"nome": "JOÃO", "email": "report@example.test"})
        self.order("confirmada")
        for query in ("João", "JOÃO", "IMPRESSÃO", "impressão"):
            with self.subTest(query=query):
                self.assertEqual(self.container.orders.search_orders(OrderQuery(search=query)).total, 1)
                self.assertEqual(self.container.production.search_queue(search=query).total, 1)


if __name__ == "__main__":
    unittest.main()
