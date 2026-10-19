from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/squackts-test-cache")

from PySide6.QtCore import QCoreApplication, QDate, QEvent, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from repositories.clients import ClientRepository  # noqa: E402
from repositories.logs import LogRepository  # noqa: E402
from repositories.orders import OrderRepository  # noqa: E402
from repositories.products import ProductRepository  # noqa: E402
from repositories.settings import SettingsRepository  # noqa: E402
from schema import apply_schema  # noqa: E402
from services.client_service import ClientService  # noqa: E402
from services.dashboard_service import DashboardService  # noqa: E402
from services.image_service import ImageService  # noqa: E402
from services.inventory_service import InventoryService  # noqa: E402
from services.order_service import OrderService  # noqa: E402
from services.product_service import ProductService  # noqa: E402
from services.production_service import ProductionService  # noqa: E402
from ui.components import ConfirmationDialog  # noqa: E402
from ui.dialogs import ClientEditorDialog, OrderEditorDialog, ProductEditorDialog  # noqa: E402
from ui.dialogs.variant_editor import VariantEditorDialog  # noqa: E402
from ui.pages.dashboard_page import DashboardPage  # noqa: E402
from ui.pages.orders_page import OrdersPage  # noqa: E402
from ui.pages.production_page import ProductionPage  # noqa: E402


class UiFlowTests(unittest.TestCase):
    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_schema(self.conn)
        logs = LogRepository(self.conn)
        self.clients = ClientService(self.conn, ClientRepository(self.conn), logs)
        self.products = ProductService(self.conn, ProductRepository(self.conn), logs)
        self.orders = OrderService(
            self.conn,
            OrderRepository(self.conn),
            ProductRepository(self.conn),
            ClientRepository(self.conn),
            logs,
            SettingsRepository(self.conn),
        )
        self.production = ProductionService(self.conn, OrderRepository(self.conn), logs)
        self.inventory = InventoryService(self.conn)
        self.images = ImageService(Path(self.temp.name) / "images")
        self.client_id = self.clients.create_client({"nome": "Cliente teste", "email": "cliente@example.com"})
        self.product_id = self.products.create_product(self.product_payload("POD-1"))
        self.widgets: list[QWidget] = []

    def tearDown(self) -> None:
        for widget in self.widgets:
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.conn.close()
        self.temp.cleanup()

    @staticmethod
    def product_payload(sku: str) -> dict[str, object]:
        return {
            "nome": "Camisola",
            "sku": sku,
            "preco": "19.99",
            "custo": "5.00",
            "stock": 0,
            "stock_minimo": 0,
            "tipo_producao": "print_on_demand",
            "ativo": 1,
        }

    def order_payload(self, **changes: object) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "estado": "rascunho",
            "pago": 0,
            "tracking": "",
            "portes": "2.00",
            "data_prevista": "",
            "notas": "",
            "items": [{"product_id": self.product_id, "quantidade": 2}],
            **changes,
        }

    def show(self, widget: QWidget) -> QWidget:
        self.widgets.append(widget)
        widget.show()
        self.app.processEvents()
        return widget

    def test_client_save_closes_and_does_not_duplicate(self) -> None:
        dialog = ClientEditorDialog(self.clients)
        self.show(dialog)
        dialog.name.set_text("Novo cliente")
        dialog.email.set_text("novo@example.com")
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog.isVisible())
        dialog._save()
        self.assertEqual(len(self.clients.list_clients()), 2)

    def test_service_error_remains_visible_and_can_be_corrected(self) -> None:
        dialog = ClientEditorDialog(self.clients)
        self.show(dialog)
        dialog.name.set_text("Duplicado")
        dialog.email.set_text("cliente@example.com")
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.assertIn("existe", dialog.form_error.text())
        dialog._validate_form()
        self.assertIn("existe", dialog.form_error.text())
        self.assertTrue(dialog.form_actions.confirm_button.isEnabled())
        self.assertEqual(dialog.name.text(), "Duplicado")
        dialog.email.set_text("corrigido@example.com")
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_product_save_closes_and_duplicate_error_is_persistent(self) -> None:
        dialog = ProductEditorDialog(self.products)
        self.show(dialog)
        dialog.name.set_text("Outro produto")
        dialog.sku.set_text("POD-1")
        dialog._save()
        self.assertIn("existe", dialog.form_error.text())
        dialog._validate_form()
        self.assertIn("existe", dialog.form_error.text())
        dialog.sku.set_text("POD-2")
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_order_save_closes_preserves_deadline_and_variant(self) -> None:
        variant_id = self.products.create_variant(
            self.product_id,
            {"sku": "POD-1-M", "tamanho": "M", "cor": "Azul", "preco": "23.00", "custo": "6.00", "stock_on_hand": 0},
        )
        dialog = OrderEditorDialog(self.orders, self.clients, self.products, initial_client_id=self.client_id)
        self.show(dialog)
        dialog.variant_combo.input.setCurrentIndex(dialog.variant_combo.input.findData(variant_id))
        dialog.personalization.set_text("Nome do cliente")
        dialog._add_item()
        dialog.has_deadline.setChecked(True)
        dialog.deadline.setDate(QDate(2026, 12, 20))
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIsNotNone(dialog.saved_id)
        order = self.orders.get_order(dialog.saved_id)
        self.assertEqual(order["data_prevista"], "2026-12-20")
        item = self.orders.get_order_items(dialog.saved_id)[0]
        self.assertEqual(item["variant_id"], variant_id)
        self.assertEqual(item["personalization"], "Nome do cliente")
        self.assertEqual(item["preco_unit_cents"], 2300)
        dialog._save()
        self.assertEqual(len(self.orders.list_orders()), 1)

    def test_order_preview_and_save_preserve_historical_prices(self) -> None:
        order_id = self.orders.create_order(self.order_payload())
        payload = self.product_payload("POD-1")
        payload["preco"] = "99.00"
        self.products.update_product(self.product_id, payload)
        order = self.orders.get_order(order_id)
        dialog = OrderEditorDialog(self.orders, self.clients, self.products, dict(order))
        self.show(dialog)
        self.assertIn("19,99", dialog.items_table.item(0, 2).text())
        dialog.notes.input.setPlainText("Notas atualizadas")
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.orders.get_order_items(order_id)[0]["preco_unit_cents"], 1999)

    def test_dirty_editor_requires_discard_confirmation(self) -> None:
        dialog = ClientEditorDialog(self.clients)
        self.show(dialog)
        dialog.name.set_text("Por guardar")
        with patch.object(ConfirmationDialog, "exec", return_value=0):
            dialog.reject()
        self.assertTrue(dialog.isVisible())
        with patch.object(ConfirmationDialog, "exec", return_value=1):
            dialog.reject()
        self.assertFalse(dialog.isVisible())

    def test_dashboard_refresh_survives_deferred_widget_deletion(self) -> None:
        self.orders.create_order(self.order_payload())
        dashboard = DashboardPage(DashboardService(self.conn))
        self.show(dashboard)
        table = dashboard.recent_table
        for _ in range(5):
            dashboard.refresh()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.assertIs(dashboard.recent_table, table)
        self.assertEqual(table.rowCount(), 1)

    def test_orders_refresh_keeps_selection_and_payment_filter(self) -> None:
        first = self.orders.create_order(self.order_payload())
        self.orders.create_order(self.order_payload(estado="confirmada", pago=1))
        page = OrdersPage(self.orders, self.clients, self.products)
        self.show(page)
        page.refresh(select_order_id=first)
        page.refresh()
        self.assertEqual(page.selected_order_id, first)
        page.payment_filter.setCurrentIndex(1)
        self.assertEqual(len(page.orders), 1)
        self.assertEqual(page.selected_order_id, first)
        page._set_status_filter("rascunho")
        self.assertEqual(page.state_combo.currentData(), "rascunho")

    def test_production_groups_orders_and_enforces_item_art(self) -> None:
        second = self.products.create_product(self.product_payload("POD-2"))
        order_id = self.orders.create_order(
            self.order_payload(
                estado="confirmada",
                items=[
                    {"product_id": self.product_id, "quantidade": 2, "personalization": "Inicial A"},
                    {"product_id": second, "quantidade": 3},
                ],
            )
        )
        page = ProductionPage(self.production, self.inventory)
        self.show(page)
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.queue[0]["units"], 5)
        tasks = self.inventory.list_tasks(order_id)
        item = next(task for task in tasks if int(task["art_required"]))
        with patch.object(ConfirmationDialog, "exec", return_value=1):
            page._task_action(int(item["order_item_id"]), "complete")
        self.assertEqual(int(self.inventory.list_tasks(order_id)[0]["qc_approved"]), 0)
        with patch.object(ConfirmationDialog, "exec", return_value=1):
            page._task_action(int(item["order_item_id"]), "art")
            page._task_action(int(item["order_item_id"]), "complete")
        updated = next(
            task
            for task in self.inventory.list_tasks(order_id)
            if int(task["order_item_id"]) == int(item["order_item_id"])
        )
        self.assertEqual(updated["status"], "concluida")

    def test_variant_editor_creates_selectable_variant(self) -> None:
        dialog = VariantEditorDialog(self.products, self.product_id)
        self.show(dialog)
        dialog.sku.set_text("POD-1-L")
        dialog.size_field.set_text("L")
        dialog.color.set_text("Verde")
        dialog.price.set_value(25)
        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.products.list_variants(self.product_id)), 2)
