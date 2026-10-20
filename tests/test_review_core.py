from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from config import AppPaths
from schema import apply_schema
from service_container import bootstrap_infrastructure
from services.order_queries import OrderQuery


class ReviewCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name)
        self.container = bootstrap_infrastructure(AppPaths.from_home(self.home), migrate_legacy=False)
        self.client = self.container.clients.create_client({"nome": "Cliente", "email": "review@example.test"})
        self.product = self.container.products.create_product({
            "nome": "Camisola", "sku": "BASE", "preco": "12.34", "custo": "3", "tipo_producao": "print_on_demand",
        })

    def tearDown(self) -> None:
        self.container.close()
        self.directory.cleanup()

    def payload(self, **changes: object) -> dict[str, object]:
        return {"client_id": self.client, "estado": "confirmada", "items": [{"product_id": self.product, "quantidade": 1}], **changes}

    def test_draft_cannot_be_paid_at_creation_or_later(self) -> None:
        with self.assertRaises(ValueError):
            self.container.orders.create_order(self.payload(estado="rascunho", pago=1))
        order = self.container.orders.create_order(self.payload(estado="rascunho"))
        with self.assertRaises(ValueError):
            self.container.orders.set_payment(order, True)
        self.assertEqual(self.container.orders.get_order(order)["pago"], 0)
        self.assertFalse(self.container.conn.in_transaction)

    def test_dispatched_order_cannot_be_cancelled(self) -> None:
        orders = self.container.orders
        order = orders.create_order(self.payload(pago=1))
        orders.mark_produced(order)
        orders.update_tracking(order, "TRACK")
        orders.dispatch_order(order)
        before = [dict(row) for row in orders.get_order_history(order)]
        with self.assertRaises(ValueError):
            orders.cancel_order(order)
        self.assertEqual(orders.get_order(order)["estado"], "expedida")
        self.assertEqual(before, [dict(row) for row in orders.get_order_history(order)])

    def test_same_product_with_distinct_art_remains_two_independent_tasks(self) -> None:
        orders, inventory = self.container.orders, self.container.inventory
        order = orders.create_order(self.payload(items=[
            {"product_id": self.product, "quantidade": 2, "artwork_path": "originals/first.png"},
            {"product_id": self.product, "quantidade": 3, "artwork_path": "originals/second.png"},
        ]))
        items = orders.get_order_items(order)
        self.assertEqual([row["quantidade"] for row in items], [2, 3])
        inventory.approve_art(int(items[0]["id"]))
        tasks = inventory.list_tasks(order)
        self.assertEqual(sorted(int(task["art_approved"]) for task in tasks), [0, 1])
        with self.assertRaises(ValueError):
            orders.start_production(order)

    def test_archived_variant_rejected_without_partial_order(self) -> None:
        variant = self.container.products.create_variant(self.product, {"sku": "INACTIVE", "ativo": 0})
        with self.assertRaises(ValueError):
            self.container.orders.create_order(self.payload(items=[{"product_id": self.product, "variant_id": variant, "quantidade": 1}]))
        self.assertEqual(self.container.orders.list_orders(), [])
        self.assertFalse(self.container.conn.in_transaction)

    def test_percent_and_underscore_are_literal_search_characters(self) -> None:
        first = self.container.orders.create_order(self.payload(notas="a%b_c"))
        self.container.orders.create_order(self.payload(notas="axbzc"))
        for literal in ("%", "_"):
            with self.subTest(literal=literal):
                result = self.container.orders.search_orders(OrderQuery(search=literal))
                self.assertEqual([row["id"] for row in result.rows], [first])

    def test_extreme_fractional_and_merged_quantities_are_validation_errors(self) -> None:
        for quantity in (10**50, float("inf"), "1.5", 0, -1):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.container.orders.create_order(self.payload(items=[{"product_id": self.product, "quantidade": quantity}]))
            self.assertFalse(self.container.conn.in_transaction)
        with self.assertRaises(ValueError):
            self.container.orders.create_order(self.payload(items=[
                {"product_id": self.product, "quantidade": 999999},
                {"product_id": self.product, "quantidade": 1},
            ]))
        self.assertEqual(self.container.orders.list_orders(), [])

    def test_total_and_shipping_overflow_roll_back_as_validation_errors(self) -> None:
        self.container.products.update_product(self.product, {"preco": "92233720368547758.07"})
        for quantity, shipping in ((2, "0"), (1, "0.01")):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.container.orders.create_order(self.payload(portes=shipping, items=[{"product_id": self.product, "quantidade": quantity}]))
            self.assertFalse(self.container.conn.in_transaction)
        self.assertEqual(self.container.orders.list_orders(), [])

    def test_cancel_paid_order_keeps_receipt_and_requires_explicit_refund(self) -> None:
        orders = self.container.orders
        order = orders.create_order(self.payload(pago=1))
        with self.assertRaises(ValueError):
            orders.record_refund(order)
        orders.cancel_order(order)
        orders.cancel_order(order)
        row = orders.get_order(order)
        self.assertEqual((row["pago"], row["refund_status"], row["refund_recorded_at"]), (1, "pending", ""))
        summary = self.container.dashboard.get_summary()
        self.assertEqual((summary.total_received, summary.refunds_pending, summary.total_refunded), (Decimal("12.34"), Decimal("12.34"), Decimal("0")))
        orders.record_refund(order)
        timestamp = orders.get_order(order)["refund_recorded_at"]
        orders.record_refund(order)
        self.assertTrue(timestamp)
        self.assertEqual(timestamp, orders.get_order(order)["refund_recorded_at"])
        self.assertEqual(sum(row["acao"] == "refund" for row in orders.get_order_history(order)), 1)
        summary = self.container.dashboard.get_summary()
        self.assertEqual((summary.total_received, summary.refunds_pending, summary.total_refunded), (Decimal("12.34"), Decimal("0"), Decimal("12.34")))

    def test_unpaid_cancellation_has_no_refund(self) -> None:
        order = self.container.orders.create_order(self.payload())
        self.container.orders.cancel_order(order)
        with self.assertRaises(ValueError):
            self.container.orders.record_refund(order)
        self.assertEqual(self.container.orders.get_order(order)["refund_status"], "none")

    def test_version_six_migration_marks_paid_cancelled_as_pending(self) -> None:
        order = self.container.orders.create_order(self.payload(pago=1))
        self.container.orders.cancel_order(order)
        conn = self.container.conn
        conn.execute("ALTER TABLE orders DROP COLUMN refund_status")
        conn.execute("ALTER TABLE orders DROP COLUMN refund_recorded_at")
        conn.execute("PRAGMA user_version=6")
        conn.commit()
        apply_schema(conn)
        row = self.container.orders.get_order(order)
        self.assertEqual((row["pago"], row["refund_status"], row["total_cents"]), (1, "pending", 1234))
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_image_limit_is_checked_before_decoding(self) -> None:
        header = Mock(width=8001, height=5000)
        with patch("services.image_service.Image.open") as opened:
            opened.return_value.__enter__.return_value = header
            with self.assertRaisesRegex(ValueError, "40 megap"):
                self.container.images.import_image(self.home / "oversized.png")
            header.load.assert_not_called()

    def test_exif_orientation_is_applied_to_managed_image(self) -> None:
        source = self.home / "rotated.jpg"
        image = Image.new("RGB", (2, 3), "red")
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        managed = self.container.images.import_image(source)
        self.assertEqual((managed.width, managed.height), (3, 2))
        with Image.open(self.container.images.resolve(managed.image_path)) as imported:
            self.assertEqual(imported.size, (3, 2))
            self.assertIsNone(imported.getexif().get(274))
