from __future__ import annotations

import csv
from pathlib import Path
from sqlite3 import Row

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from services.product_service import ProductService
from ui.components import (
    DataTable,
    DetailPanel,
    EmptyState,
    InfoRow,
    PageHeader,
    PanelHeader,
    PlaceholderThumbnail,
    PrimaryButton,
    SearchInput,
    StatPill,
    Toolbar,
    show_toast,
)
from ui.dialogs import ProductEditorDialog
from ui.theme import SPACING
from utils import format_currency


class ProductsPage(QWidget):
    def __init__(self, service: ProductService) -> None:
        super().__init__()
        self.service = service
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
        root.addWidget(PageHeader("Catálogo", "Gestão comercial de produtos, margens e produção."))
        self.search_input = SearchInput("Pesquisar produto, SKU ou coleção...")
        self.search_input.textChanged.connect(self.apply_search)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["todas", "print_on_demand", "stock_fisico", "misto"])
        self.type_combo.currentTextChanged.connect(self._set_type_filter)
        self.export_button = PrimaryButton("Exportar CSV")
        self.export_button.clicked.connect(self._export_csv)
        root.addWidget(Toolbar(self.search_input, self.type_combo, self.export_button, StatPill("Dados reais", "ok"), add_button))

        body = QHBoxLayout()
        body.setSpacing(SPACING.md)

        table_card = QWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(PanelHeader("Produtos", "Dados reais da base de dados"))

        self.table = DataTable(0, 6)
        self.table.setHorizontalHeaderLabels(["Produto", "Cor", "SKU", "Produção", "Preço", "Margem"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.empty = EmptyState("Sem produtos", "Crie o primeiro produto para iniciar o catálogo.")
        table_layout.addWidget(self.table)
        table_layout.addWidget(self.empty)
        body.addWidget(table_card, stretch=3)

        self.detail = DetailPanel("Produto selecionado")
        self.detail.add_content_widget(PanelHeader("Nenhum produto", "Selecione um item na tabela", PlaceholderThumbnail("POD")))
        body.addWidget(self.detail, stretch=2)

        root.addLayout(body)
        self.refresh()

    def refresh(self, select_product_id: int | None = None) -> None:
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
            margin = ((float(row["preco"]) - float(row["custo"])) / float(row["preco"]) * 100.0) if float(row["preco"]) else 0.0
            values = [
                str(row["nome"]),
                str(row["cor"]),
                str(row["sku"]),
                str(row["tipo_producao"]),
                format_currency(float(row["preco"])),
                f"{margin:.1f}%",
            ]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))

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
        self.table.selectRow(target_row)

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def _filtered_products(self) -> list[Row]:
        rows = list(self.products_all)
        if self.type_filter != "todas":
            rows = [row for row in rows if str(row["tipo_producao"]) == self.type_filter]
        if not self.search_text:
            return rows
        return [
            row
            for row in rows
            if self.search_text in str(row["nome"]).lower()
            or self.search_text in str(row["sku"]).lower()
            or self.search_text in str(row["cor"]).lower()
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
                writer.writerow(["id", "sku", "nome", "cor", "tamanhos", "tipo_producao", "preco", "custo", "stock", "stock_minimo", "ativo"])
                for row in self.products:
                    writer.writerow(
                        [
                            row["id"],
                            row["sku"],
                            row["nome"],
                            row["cor"],
                            self._sizes_label(row),
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

        self.detail.add_content_widget(PanelHeader(str(product["nome"]), str(product["sku"]), self._image_preview_widget(str(product["image_path"]))))
        self.detail.add_content_widget(InfoRow("Cor", str(product["cor"]) or "-"))
        self.detail.add_content_widget(InfoRow("Tamanhos", self._sizes_label(product)))
        self.detail.add_content_widget(InfoRow("Tipo produção", str(product["tipo_producao"])))
        self.detail.add_content_widget(InfoRow("Preço", format_currency(float(product["preco"]))))
        self.detail.add_content_widget(InfoRow("Custo", format_currency(float(product["custo"]))))
        self.detail.add_content_widget(InfoRow("Stock", str(product["stock"])))
        self.detail.add_content_widget(InfoRow("Stock mínimo", str(product["stock_minimo"])))
        self.detail.add_content_widget(InfoRow("Imagem", str(product["image_path"]) or "-"))
        self.detail.add_content_widget(InfoRow("Descrição", str(product["descricao"]) or "-"))

        edit_button = PrimaryButton("Editar produto")
        edit_button.clicked.connect(self._open_edit)
        self.detail.add_content_widget(edit_button)

    def _open_create(self) -> None:
        dialog = ProductEditorDialog(self.service, parent=self)
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
        dialog = ProductEditorDialog(self.service, product=dict(row), parent=self)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_product_id=dialog.saved_id)
            show_toast(self, "Produto atualizado", "ok")


    def _image_preview_widget(self, image_path: str) -> QWidget:
        if not image_path:
            return PlaceholderThumbnail("POD")
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return PlaceholderThumbnail("POD")
        label = QLabel()
        label.setFixedSize(56, 56)
        label.setAlignment(Qt.AlignCenter)
        label.setPixmap(pixmap.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return label
    def _sizes_label(self, product: Row) -> str:
        import json

        raw = product["tamanhos_json"]
        if not raw:
            return "-"
        try:
            decoded = json.loads(str(raw))
        except Exception:
            return "-"
        if not isinstance(decoded, list) or not decoded:
            return "-"
        return ", ".join(str(item) for item in decoded)
