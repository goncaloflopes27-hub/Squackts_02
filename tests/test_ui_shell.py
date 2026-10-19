from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLineEdit, QStyleOptionViewItem, QWidget

from config import AppPaths
from service_container import bootstrap_infrastructure
from ui.animations import animate_dialog_close, fade_in
from ui.components import DataTable, InfoRow
from ui.main_window import MainWindow
from ui.preferences import PreferencesDialog


class UiShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.qt_messages: list[str] = []
        self._previous_handler = qInstallMessageHandler(
            lambda _kind, _context, message: self.qt_messages.append(message)
        )
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        paths = AppPaths(
            base_dir=root, data_dir=root / "data", backups_dir=root / "backups",
            images_dir=root / "images", logs_dir=root / "logs",
            db_path=root / "data" / "app.db", log_file_path=root / "logs" / "app.log",
        )
        self.container = bootstrap_infrastructure(paths=paths, migrate_legacy=False)
        self.container.preferences.set("ui.reduce_motion", "1")
        self.client_id = self.container.clients.create_client({"nome": "Estúdio Aurora", "email": "aurora@example.test", "ativo": 1})
        self.product_id = self.container.products.create_product({
            "nome": "T-shirt Essencial", "sku": "TS-001", "preco": "24.90", "custo": "8.50",
            "stock": 20, "stock_minimo": 5, "tipo_producao": "stock_fisico", "ativo": 1,
        })
        self.order_id = self.container.orders.create_order({
            "client_id": self.client_id, "estado": "confirmada", "pago": 0, "portes": "4.50",
            "items": [{"product_id": self.product_id, "quantidade": 3}],
        })
        self.window = MainWindow(self.container)
        self.window.resize(1280, 800)
        self.window.show()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.container.conn.close()
        self.directory.cleanup()
        qInstallMessageHandler(self._previous_handler)

    def test_all_six_pages_refresh_repeatedly_without_deleted_widgets_or_invalid_styles(self) -> None:
        for _ in range(3):
            for key in self.window.page_refs:
                self.window.navigate(key)
                self.window.refresh_current()
                self.app.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertEqual(self.window.current_page_key, key)
                self.assertTrue(self.window.sidebar._buttons[key].isChecked())
                self.assertEqual(self.window.page_scrolls[key].horizontalScrollBar().maximum(), 0)
        self.assertEqual(self.window.size().width(), 1280)
        self.assertEqual(self.window.size().height(), 800)
        self.assertFalse(any("Could not parse stylesheet" in message for message in self.qt_messages), self.qt_messages)

    def test_search_is_contextual_and_preserved_per_page(self) -> None:
        self.window.navigate("clients")
        self.window.topbar.search.setText("Aurora")
        self.window.navigate("products")
        self.assertEqual(self.window.topbar.search.text(), "")
        self.window.topbar.search.setText("T-shirt")
        self.window.navigate("clients")
        self.assertEqual(self.window.topbar.search.text(), "Aurora")
        self.assertEqual(self.window.page_refs["clients"].search_text, "aurora")
        self.window.navigate("products")
        self.assertEqual(self.window.topbar.search.text(), "T-shirt")
        self.assertEqual(self.window.page_refs["products"].search_text, "t-shirt")
        self.assertFalse(self.window.page_refs["products"].search_input.isVisible())

    def test_change_events_from_worker_refresh_widgets_on_main_thread(self) -> None:
        self.window.navigate("clients")
        page = self.window.page_refs["clients"]
        calls: list[int] = []
        original = page.refresh

        def record_refresh() -> None:
            calls.append(threading.get_ident())
            original()

        with patch.object(page, "refresh", side_effect=record_refresh):
            worker = threading.Thread(target=lambda: self.container.events.emit("clients"))
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            QTest.qWait(40)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {threading.get_ident()})
        self.assertIn("orders", self.window._dirty)
        self.window.navigate("orders")
        self.assertNotIn("orders", self.window._dirty)

    def test_read_only_tables_allow_only_explicit_editor_columns(self) -> None:
        table = DataTable(1, 5)
        self.assertEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
        table.set_editable_columns({3})
        delegate = table.itemDelegate()
        blocked = delegate.createEditor(table, QStyleOptionViewItem(), table.model().index(0, 0))
        editor = delegate.createEditor(table, QStyleOptionViewItem(), table.model().index(0, 3))
        self.assertIsNone(blocked)
        self.assertIsInstance(editor, QLineEdit)
        table.deleteLater()

    def test_preferences_persist_and_reduced_motion_finishes_callbacks(self) -> None:
        dialog = PreferencesDialog(self.container.preferences, self.window)
        dialog.reduce_motion.setChecked(True)
        dialog.compact_sidebar.setChecked(True)
        dialog._save()
        self.window._apply_preferences()
        self.assertEqual(self.container.preferences.get("ui.compact_sidebar"), "1")
        self.assertTrue(self.window.sidebar._compact)
        widget = QWidget(self.window)
        widget.show()
        animation = fade_in(widget)
        self.assertEqual(animation.duration(), 0)
        completed: list[bool] = []
        animate_dialog_close(widget, lambda: completed.append(True))
        self.app.processEvents()
        self.assertEqual(completed, [True])
        dialog.deleteLater()
        widget.deleteLater()

    def test_detail_values_receive_space_and_remain_readable(self) -> None:
        row = InfoRow("Data prevista", "Sem prazo")
        row.setParent(self.window)
        row.resize(400, 50)
        row.show()
        self.app.processEvents()
        value = row.layout().itemAt(1).widget()
        self.assertTrue(value.isVisible())
        self.assertGreater(value.width(), 100)
        row.deleteLater()

    def test_keyboard_navigation_and_alerts_have_real_destinations(self) -> None:
        self.window.activateWindow()
        QTest.qWait(20)
        QTest.keyClick(self.window, Qt.Key.Key_3, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.window.current_page_key, "products")
        QTest.keyClick(self.window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.topbar.search.hasFocus())
        self.window.topbar.alerts_button.click()
        self.assertEqual(self.window.current_page_key, "dashboard")
        self.window.resize(1600, 960)
        self.app.processEvents()
        self.assertFalse(self.window.sidebar._compact)
        self.window.resize(1280, 800)
        self.app.processEvents()
        self.assertTrue(self.window.sidebar._compact)


if __name__ == "__main__":
    unittest.main()
