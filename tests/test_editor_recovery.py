from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QRect, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from config import AppPaths  # noqa: E402
from service_container import bootstrap_infrastructure  # noqa: E402
from ui.components import ConfirmationDialog  # noqa: E402
from ui.dialogs import ClientEditorDialog, OrderEditorDialog, ProductEditorDialog  # noqa: E402
from ui.dialogs.variant_editor import VariantEditorDialog  # noqa: E402
from ui.error_reporting import install_exception_handler  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


class EditorRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name)
        self.container = bootstrap_infrastructure(AppPaths.from_home(self.home), migrate_legacy=False)
        self.client = self.container.clients.create_client({"nome": "Cliente", "email": "base@example.test"})
        self.product = self.container.products.create_product({"nome": "POD", "sku": "BASE", "preco": "10", "custo": "3"})
        self.dialogs = []

    def tearDown(self) -> None:
        for dialog in self.dialogs:
            dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.container.close()
        self.directory.cleanup()

    def editor(self, kind: str, index: int):
        if kind == "client":
            dialog = ClientEditorDialog(self.container.clients)
            dialog.name.set_text("Cliente preenchido")
            dialog.email.set_text(f"new{index}@example.test")
            service, method, error = self.container.clients, "create_client", dialog.form_error
        elif kind == "product":
            dialog = ProductEditorDialog(self.container.products)
            dialog.name.set_text("Produto preenchido")
            dialog.sku.set_text(f"PRODUCT-{index}")
            service, method, error = self.container.products, "create_product", dialog.form_error
        elif kind == "order":
            dialog = OrderEditorDialog(self.container.orders, self.container.clients, self.container.products, initial_client_id=self.client)
            dialog._add_item()
            service, method, error = self.container.orders, "create_order", dialog.error
        else:
            dialog = VariantEditorDialog(self.container.products, self.product)
            dialog.sku.set_text(f"VARIANT-{index}")
            service, method, error = self.container.products, "create_variant", dialog.error
        self.dialogs.append(dialog)
        dialog.show()
        self.app.processEvents()
        return dialog, service, method, error

    def test_all_editors_unlock_preserve_fields_and_retry_after_unexpected_errors(self) -> None:
        for kind in ("client", "product", "order", "variant"):
            for index, failure in enumerate((sqlite3.OperationalError("database is locked"), OverflowError("huge"), RuntimeError("unexpected"))):
                with self.subTest(kind=kind, failure=type(failure).__name__):
                    dialog, service, method, error = self.editor(kind, index)
                    snapshot = dialog._snapshot()
                    with patch.object(service, method, side_effect=failure), self.assertLogs("squackts.ui", level="ERROR"):
                        QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
                    self.assertFalse(dialog._saving)
                    self.assertTrue(dialog.form_actions.confirm_button.isEnabled())
                    self.assertTrue(error.text())
                    self.assertEqual(dialog._snapshot(), snapshot)
                    QTest.mouseClick(dialog.form_actions.confirm_button, Qt.MouseButton.LeftButton)
                    self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_failed_editor_can_be_closed_after_discard_confirmation(self) -> None:
        dialog, service, method, _error = self.editor("client", 0)
        with patch.object(service, method, side_effect=sqlite3.OperationalError("disk full")), self.assertLogs("squackts.ui", level="ERROR"):
            dialog._save()
        with patch.object(ConfirmationDialog, "exec", return_value=1):
            dialog.reject()
        self.assertFalse(dialog.isVisible())

    def test_payload_failure_also_releases_the_save_guard(self) -> None:
        dialog, _service, _method, _error = self.editor("product", 0)
        with patch.object(dialog, "_payload", side_effect=RuntimeError("payload")), self.assertLogs("squackts.ui", level="ERROR"):
            dialog._save()
        self.assertFalse(dialog._saving)
        self.assertTrue(dialog.form_actions.confirm_button.isEnabled())

    def test_global_callback_error_is_logged_and_visible(self) -> None:
        previous = sys.excepthook
        restore = install_exception_handler(self.app, self.home / "logs" / "app.log")
        try:
            with self.assertLogs("squackts.ui", level="CRITICAL"):
                sys.excepthook(RuntimeError, RuntimeError("callback"), None)
            self.app.processEvents()
            notices = [item for item in self.app.topLevelWidgets() if isinstance(item, QMessageBox) and item.isVisible()]
            self.assertEqual(len(notices), 1)
            self.assertIn("app.log", notices[0].informativeText())
        finally:
            restore()
        self.assertIs(sys.excepthook, previous)

    def test_window_minimum_fits_a_1366_by_728_work_area(self) -> None:
        window = MainWindow(self.container, available_geometry=QRect(0, 0, 1366, 728))
        self.dialogs.append(window)
        window.resize(1280, 728)
        window.show()
        self.app.processEvents()
        self.assertLessEqual(window.minimumHeight(), 728)
        self.assertLessEqual(window.height(), 728)

    def test_order_editor_fits_work_area_with_save_actions_accessible(self) -> None:
        dialog, _service, _method, _error = self.editor("order", 0)
        dialog.resize(980, 780)
        dialog._fit_to_screen(QRect(0, 0, 1366, 728))
        self.app.processEvents()
        self.assertLessEqual(dialog.height(), 680)
        button = dialog.form_actions.confirm_button
        self.assertTrue(button.isVisible())
        self.assertLessEqual(button.mapTo(dialog, button.rect().bottomRight()).y(), dialog.height())
