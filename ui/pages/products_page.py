from __future__ import annotations

import csv
from pathlib import Path
from sqlite3 import Row

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from services.image_service import ImageService
from services.product_service import ProductService
from ui.components import (
    ActivityList,
    ConfirmationDialog,
    DetailPanel,
    EmptyState,
    InfoRow,
    PageHeader,
    PanelHeader,
    PlaceholderThumbnail,
    PrimaryButton,
    RecordTable,
    SearchInput,
    SecondaryButton,
    Toolbar,
    show_toast,
)
from ui.dialogs import ProductEditorDialog
from ui.dialogs.variant_editor import VariantEditorDialog
from ui.theme import SPACING
from utils import format_currency


class ProductsPage(QWidget):
    def __init__(self, service: ProductService, image_service: ImageService | None = None) -> None:
        super().__init__()
        self.service = service
        self.image_service = image_service
        self.products: list[Row] = []
        self.products_all: list[Row] = []
        self.selected_product_id: int | None = None
        self.search_text = ""
        self.type_filter = "todas"
        self._loading_error: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)

        add_button = PrimaryButton("Novo produto")
        add_button.clicked.connect(self._open_create)
        root.addWidget(PageHeader("Catálogo", "As tuas peças, preços e disponibilidade."))
        self.search_input = SearchInput("Pesquisar produto, SKU ou coleção...")
        self.search_input.textChanged.connect(self.apply_search)
        self.type_combo = QComboBox()
        for label, value in [
            ("Todos os tipos de produção", "todas"),
            ("Produzir a pedido", "print_on_demand"),
            ("Stock físico", "stock_fisico"),
            ("Misto", "misto"),
        ]:
            self.type_combo.addItem(label, value)
        self.type_combo.currentIndexChanged.connect(
            lambda _index: self._set_type_filter(str(self.type_combo.currentData()))
        )
        self.active_combo = QComboBox()
        self.active_combo.addItems(["Ativos", "Arquivados", "Todos"])
        self.active_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.stock_combo = QComboBox()
        self.stock_combo.addItems(["Todo o stock", "Stock baixo", "Disponível"])
        self.stock_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.export_button = SecondaryButton("Exportar CSV")
        self.export_button.clicked.connect(self._export_csv)
        root.addWidget(
            Toolbar(self.search_input, self.type_combo, self.active_combo, self.stock_combo)
        )
        root.addWidget(Toolbar(self.export_button, add_button))

        body = QHBoxLayout()
        body.setSpacing(SPACING.md)

        table_card = QWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(PanelHeader("Produtos", "Preços e disponibilidade num só olhar"))

        self.table = RecordTable(0, 7)
        self.table.setHorizontalHeaderLabels(["Produto", "SKU", "Produção", "Preço", "Custo", "Margem", "Disponível"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.empty = EmptyState("Sem produtos", "Crie o primeiro produto para iniciar o catálogo.")
        table_layout.addWidget(self.table)
        table_layout.addWidget(self.empty)
        body.addWidget(table_card, stretch=3)

        self.detail = DetailPanel("Produto selecionado")
        self.detail.add_content_widget(
            PanelHeader("Nenhum produto", "Selecione um item na tabela", PlaceholderThumbnail("POD"))
        )
        body.addWidget(self.detail, stretch=2)

        root.addLayout(body)
        self.refresh()

    def refresh(self, select_product_id: int | None = None) -> None:
        select_product_id = select_product_id if select_product_id is not None else self.selected_product_id
        scroll = self.table.verticalScrollBar().value()
        self.table.blockSignals(True)
        try:
            self.products_all = self.service.list_products()
            self._loading_error = None
        except Exception as exc:
            self.products_all = []
            self._loading_error = f"Erro ao carregar catálogo: {exc}"
            show_toast(self, self._loading_error, "danger")
        self.products = self._filtered_products()
        self.table.setRowCount(len(self.products))
        for i, row in enumerate(self.products):
            margin = (
                ((float(row["preco"]) - float(row["custo"])) / float(row["preco"]) * 100.0)
                if float(row["preco"])
                else 0.0
            )
            values = [
                str(row["nome"]),
                str(row["sku"]),
                {"print_on_demand": "A pedido", "stock_fisico": "Stock físico", "misto": "Misto"}.get(
                    str(row["tipo_producao"]), str(row["tipo_producao"])
                ),
                format_currency(float(row["preco"])),
                format_currency(float(row["custo"])),
                f"{margin:.1f}%",
                "A produzir"
                if str(row["tipo_producao"]) == "print_on_demand"
                else str(dict(row).get("stock_available", row["stock"])),
            ]
            for j, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if j == 0 and self.image_service and str(row["image_path"]):
                    try:
                        cell.setIcon(QIcon(str(self.image_service.resolve(str(row["image_path"])))))
                    except ValueError:
                        pass
                self.table.setItem(i, j, cell)

        self.table.blockSignals(False)
        is_empty = len(self.products) == 0
        self.table.setVisible(not is_empty)
        self.empty.setVisible(is_empty)
        self.export_button.setEnabled(not is_empty)

        if is_empty:
            self.selected_product_id = None
            if self._loading_error:
                self.empty.set_content("Erro ao carregar", self._loading_error)
            elif self.search_text or self.type_filter != "todas":
                self.empty.set_content("Sem resultados", "Ajuste pesquisa/filtro para encontrar produtos.")
            else:
                self.empty.set_content("Sem produtos", "Crie o primeiro produto para iniciar o catálogo.")
            self._render_detail(None)
            return

        target_row = 0
        if select_product_id is not None:
            for idx, product in enumerate(self.products):
                if int(product["id"]) == select_product_id:
                    target_row = idx
                    break
        self.table.blockSignals(True)
        self.table.selectRow(target_row)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll)
        self._on_selection_changed()

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def _filtered_products(self) -> list[Row]:
        rows = list(self.products_all)
        if self.active_combo.currentIndex() != 2:
            active = self.active_combo.currentIndex() == 0
            rows = [row for row in rows if bool(int(row["ativo"])) == active]
        if self.stock_combo.currentIndex() == 1:
            rows = [
                row
                for row in rows
                if str(row["tipo_producao"]) != "print_on_demand" and int(row["stock"]) <= int(row["stock_minimo"])
            ]
        elif self.stock_combo.currentIndex() == 2:
            rows = [row for row in rows if str(row["tipo_producao"]) == "print_on_demand" or int(row["stock"]) > 0]
        if self.type_filter != "todas":
            rows = [row for row in rows if str(row["tipo_producao"]) == self.type_filter]
        if not self.search_text:
            return rows
        return [
            row
            for row in rows
            if self.search_text in str(row["nome"]).lower() or self.search_text in str(row["sku"]).lower()
        ]

    def _set_type_filter(self, value: str) -> None:
        self.type_filter = value
        self.refresh()

    def _export_csv(self) -> None:
        if not self.products:
            show_toast(self, "Sem produtos para exportar", "warning")
            return
        target, _ = QFileDialog.getSaveFileName(self, "Exportar catálogo", "produtos.csv", "CSV (*.csv)")
        if not target:
            return
        csv_path = Path(target)
        try:
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["id", "sku", "nome", "tipo_producao", "preco", "custo", "stock", "stock_minimo", "ativo"]
                )
                for row in self.products:
                    writer.writerow(
                        [
                            row["id"],
                            row["sku"],
                            row["nome"],
                            row["tipo_producao"],
                            float(row["preco"]),
                            float(row["custo"]),
                            int(row["stock"]),
                            int(row["stock_minimo"]),
                            int(row["ativo"]),
                        ]
                    )
        except OSError as exc:
            show_toast(self, f"Falha ao exportar catálogo: {exc}", "danger")
            return
        show_toast(self, f"Catálogo exportado: {csv_path.name}", "ok")

    def _on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
        row = selected_items[0].row()
        if row >= len(self.products):
            return
        product = self.products[row]
        self.selected_product_id = int(product["id"])
        self._render_detail(product)

    def _render_detail(self, product: Row | None) -> None:
        self.detail.clear_content()

        if product is None:
            self.detail.add_content_widget(InfoRow("Estado", "Sem seleção"))
            return

        thumbnail = QLabel()
        thumbnail.setFixedSize(72, 72)
        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.image_service and str(product["image_path"]):
            try:
                pixmap = QPixmap(str(self.image_service.resolve(str(product["image_path"]))))
                thumbnail.setPixmap(
                    pixmap.scaled(
                        72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )
            except ValueError:
                thumbnail.setText("POD")
        else:
            thumbnail.setText("POD")
        self.detail.add_content_widget(PanelHeader(str(product["nome"]), str(product["sku"]), thumbnail))
        self.detail.add_content_widget(
            InfoRow(
                "Modo de tratamento",
                {
                    "print_on_demand": "Produzir a pedido",
                    "stock_fisico": "Stock físico",
                    "misto": "Stock e produção",
                }.get(str(product["tipo_producao"]), str(product["tipo_producao"])),
            )
        )
        self.detail.add_content_widget(InfoRow("Preço", format_currency(float(product["preco"]))))
        self.detail.add_content_widget(InfoRow("Custo", format_currency(float(product["custo"]))))
        self.detail.add_content_widget(InfoRow("Stock", str(product["stock"])))
        self.detail.add_content_widget(InfoRow("Stock mínimo", str(product["stock_minimo"])))
        self.detail.add_content_widget(InfoRow("Imagem", str(product["image_path"]) or "-"))
        self.detail.add_content_widget(InfoRow("Descrição", str(product["descricao"]) or "-"))

        edit_button = PrimaryButton("Editar produto")
        edit_button.clicked.connect(self._open_edit)
        self.detail.add_content_widget(edit_button)
        if int(product["ativo"]):
            archive = SecondaryButton("Arquivar produto")
            archive.clicked.connect(self._archive_selected)
            self.detail.add_content_widget(archive)
        variants = self.service.list_variants(int(product["id"]))
        for variant in variants:
            title = " / ".join(part for part in (str(variant["tamanho"]), str(variant["cor"])) if part) or "Principal"
            self.detail.add_content_widget(
                InfoRow(
                    title,
                    f"{variant['sku']} · {variant['stock_available']} disponíveis / {variant['stock_reserved']} reservados",
                )
            )
            edit_variant = SecondaryButton(f"Editar {title}")
            edit_variant.clicked.connect(lambda _checked=False, item=dict(variant): self._edit_variant(item))
            self.detail.add_content_widget(edit_variant)
        add_variant = SecondaryButton("Nova variante de tamanho / cor")
        add_variant.setEnabled(bool(int(product["ativo"])))
        add_variant.clicked.connect(lambda: self._edit_variant(None))
        self.detail.add_content_widget(add_variant)
        variant_ids = {int(v["id"]) for v in variants}
        movements = [dict(m) for m in self.service.list_inventory_movements() if int(m["variant_id"]) in variant_ids][
            :10
        ]
        self.detail.add_content_widget(
            ActivityList(
                "Movimentos de stock",
                [
                    (
                        str(m.get("kind", m.get("movement_type", "Movimento"))).replace("_", " "),
                        str(m.get("reason", "")),
                    )
                    for m in movements
                ]
                or [("Sem movimentos", "O histórico aparece após reservas e ajustes.")],
            )
        )

    def _open_create(self) -> None:
        dialog = ProductEditorDialog(self.service, parent=self, image_service=self.image_service)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_product_id=dialog.saved_id)
            show_toast(self, "Produto criado", "ok")

    def _open_edit(self) -> None:
        if self.selected_product_id is None:
            return
        row = self.service.get_product(self.selected_product_id)
        if row is None:
            show_toast(self, "Produto não encontrado", "warning")
            return
        dialog = ProductEditorDialog(self.service, product=dict(row), parent=self, image_service=self.image_service)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_product_id=dialog.saved_id)
            show_toast(self, "Produto atualizado", "ok")

    def _archive_selected(self) -> None:
        if self.selected_product_id is None:
            return
        if not ConfirmationDialog(
            "Arquivar produto", "Retirar este produto das novas encomendas, preservando o histórico?", self
        ).exec():
            return
        try:
            self.service.archive_product(self.selected_product_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()
        show_toast(self, "Produto arquivado", "ok")

    def _edit_variant(self, variant: dict[str, object] | None) -> None:
        if self.selected_product_id is None:
            return
        dialog = VariantEditorDialog(self.service, self.selected_product_id, variant, self)
        if dialog.exec():
            self.refresh()
            show_toast(self, "Variante guardada", "ok")
