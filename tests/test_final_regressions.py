from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from config import AppPaths
from service_container import bootstrap_infrastructure
from services.image_service import ImageService


class CatalogIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.paths = AppPaths.from_home(Path(self.directory.name))
        self.container = bootstrap_infrastructure(self.paths, migrate_legacy=False)

    def tearDown(self) -> None:
        self.container.close()
        self.directory.cleanup()

    def test_metadata_edit_cannot_reintroduce_stock_reserved_by_another_connection(self) -> None:
        products = self.container.products
        client = self.container.clients.create_client({"nome": "Concurrent", "email": "race@example.test"})
        product = products.create_product({
            "nome": "Stock", "sku": "RACE", "preco": "10", "custo": "4",
            "tipo_producao": "stock_fisico", "stock": 5,
        })
        other = bootstrap_infrastructure(self.paths, migrate_legacy=False)
        original_get = products.products.get_by_id
        interleaved = False

        def reserve() -> None:
            other.orders.create_order({
                "client_id": client, "estado": "confirmada",
                "items": [{"product_id": product, "quantidade": 2}],
            })

        def read_with_competing_confirmation(product_id: int):
            nonlocal interleaved
            snapshot = original_get(product_id)
            # This interleaving is possible only when the catalog reads before
            # acquiring its write transaction. Otherwise the writes serialize.
            if not self.container.conn.in_transaction and not interleaved:
                interleaved = True
                reserve()
            return snapshot

        try:
            with patch.object(products.products, "get_by_id", side_effect=read_with_competing_confirmation):
                products.update_product(product, {"descricao": "Apenas descrição"})
            if not interleaved:
                reserve()
            row = products.get_product(product)
            assert row is not None
            self.assertEqual((row["stock_on_hand"], row["stock_reserved"], row["stock_available"]), (5, 2, 3))
        finally:
            other.close()

    def test_metadata_edits_preserve_integer_cents_beyond_float_precision(self) -> None:
        products = self.container.products
        product = products.create_product({
            "nome": "Exact", "sku": "EXACT", "preco": "90071992547409.93", "custo": "4",
            "tipo_producao": "print_on_demand", "stock": 0,
        })
        products.update_product(product, {"descricao": "Metadados"})
        base = products.get_default_variant(product)
        assert base is not None
        products.update_variant(int(base["id"]), {"cor": "Azul"})
        row = products.get_product(product)
        assert row is not None
        self.assertEqual(row["preco_cents"], 9007199254740993)

    def test_indexed_print_art_preserves_transparency_and_partial_alpha(self) -> None:
        root = Path(self.directory.name)
        source = root / "indexed.png"
        image = Image.new("P", (2, 1))
        image.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
        image.putdata([0, 1])
        image.info["transparency"] = bytes([0, 128] + [255] * 254)
        image.save(source)
        images = ImageService(root / "managed")
        managed = images.import_image(source)
        for reference in (managed.image_path, managed.thumbnail_path):
            with self.subTest(reference=reference), Image.open(images.resolve(reference)) as imported:
                self.assertEqual(imported.mode, "RGBA")
                self.assertEqual(imported.getpixel((0, 0))[3], 0)
                self.assertEqual(imported.getpixel((1, 0))[3], 128)


class RestoreFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_catalog_editors_do_not_resubmit_unchanged_stock_after_order_changes(self) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent

        from ui.dialogs.product_editor import ProductEditorDialog
        from ui.dialogs.variant_editor import VariantEditorDialog

        with tempfile.TemporaryDirectory() as directory:
            container = bootstrap_infrastructure(AppPaths.from_home(Path(directory)), migrate_legacy=False)
            client = container.clients.create_client({"nome": "Editor", "email": "editor@example.test"})
            product = container.products.create_product({
                "nome": "Stock", "sku": "EDITOR", "preco": "10", "custo": "4",
                "tipo_producao": "stock_fisico", "stock": 5,
            })
            original = container.products.get_product(product)
            assert original is not None
            editor = ProductEditorDialog(container.products, dict(original))
            base = container.products.get_default_variant(product)
            assert base is not None
            variant_editor = VariantEditorDialog(container.products, product, dict(base))
            try:
                order = container.orders.create_order({
                    "client_id": client, "estado": "confirmada",
                    "items": [{"product_id": product, "quantidade": 2}],
                })
                editor.notes.input.setPlainText("Apenas descrição")
                editor._save()
                self.assertEqual(container.products.get_product(product)["stock_available"], 3)
                container.orders.mark_ready(order)
                container.orders.set_payment(order, True)
                container.orders.update_tracking(order, "TRACK-EDITOR")
                container.orders.dispatch_order(order)
                variant_editor.color.set_text("Azul")
                variant_editor._save()
                self.assertIsNotNone(variant_editor.saved_id)
                self.assertEqual(container.products.get_product(product)["stock_on_hand"], 3)
            finally:
                editor.deleteLater()
                variant_editor.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.app.processEvents()
                container.close()

    def test_failed_restore_reports_recovery_error_without_escaping_qt_callback(self) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent

        from ui.pages.system_page import SystemPage

        with tempfile.TemporaryDirectory() as directory:
            container = bootstrap_infrastructure(AppPaths.from_home(Path(directory)), migrate_legacy=False)
            page = SystemPage(container)
            try:
                backup = container.backup.create_backup()
                with (
                    patch("ui.pages.system_page.QFileDialog.getOpenFileName", return_value=(str(backup), "")),
                    patch("ui.pages.system_page.ConfirmationDialog.exec", return_value=1),
                    patch.object(container.backup, "restore_backup", side_effect=RuntimeError("Recuperação realizada")),
                    patch("ui.pages.system_page.show_toast") as toast,
                    patch("ui.pages.system_page.QMessageBox.information") as success,
                ):
                    page._restore_backup()
                    self.assertIn("Restauro não realizado", toast.call_args.args[1])
                    success.assert_not_called()
                    self.assertTrue(container.backup.get_diagnostics().connection_ok)
            finally:
                page.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.app.processEvents()
                container.close()


if __name__ == "__main__":
    unittest.main()
