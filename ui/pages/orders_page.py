from __future__ import annotations

import csv
from pathlib import Path
from sqlite3 import Row

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QTableWidgetItem, QVBoxLayout, QWidget

from services.client_service import ClientService
from services.order_domain import ORDERED_STATES, TRACKING_ALLOWED_STATES
from services.order_service import OrderService
from services.product_service import ProductService
from ui.components import (
    ActivityList,
    ConfirmationDialog,
    DataTable,
    DetailPanel,
    EmptyState,
    GhostButton,
    InfoRow,
    PageHeader,
    PanelHeader,
    PrimaryButton,
    SearchInput,
    SecondaryButton,
    Toolbar,
    show_toast,
)
from ui.dialogs import OrderEditorDialog
from ui.theme import SPACING
from utils import format_currency


class OrdersPage(QWidget):
    def __init__(self, order_service: OrderService, client_service: ClientService, product_service: ProductService) -> None:
        super().__init__()
        self.order_service = order_service
        self.client_service = client_service
        self.product_service = product_service
        self.orders: list[Row] = []
        self.orders_all: list[Row] = []
        self.selected_order_id: int | None = None
        self.search_text = ""
        self.status_filter = "todas"
        self._loading_error: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)

        root.addWidget(PageHeader("Encomendas", "Execução operacional com stock e produção reais."))

        self.new_button = PrimaryButton("Nova encomenda")
        self.new_button.clicked.connect(self._open_create)
        self.search_input = SearchInput("Pesquisar encomenda...")
        self.search_input.textChanged.connect(self.apply_search)
        self.state_combo = QComboBox()
        self.state_combo.addItems(["todas", *ORDERED_STATES])
        self.state_combo.currentTextChanged.connect(self._set_status_filter)
        self.export_button = SecondaryButton("Exportar")
        self.export_button.clicked.connect(self._export_csv)
        root.addWidget(Toolbar(self.search_input, self.state_combo, self.export_button, self.new_button))

        body = QHBoxLayout()
        body.setSpacing(SPACING.md)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        self.table = DataTable(0, 7)
        self.table.setHorizontalHeaderLabels(["Número", "Cliente", "Itens", "Estado", "Tracking", "Pago", "Total"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left.addWidget(self.table)
        self.empty = EmptyState("Sem resultados", "Não existem encomendas para os filtros/pesquisa atuais.")
        left.addWidget(self.empty)
        left_widget = QWidget()
        left_widget.setLayout(left)
        body.addWidget(left_widget, stretch=3)

        self.detail = DetailPanel("Detalhe da encomenda")
        body.addWidget(self.detail, stretch=2)

        root.addLayout(body)
        self.refresh()

    def refresh(self, select_order_id: int | None = None) -> None:
        try:
            self.orders_all = self.order_service.list_orders()
            self._loading_error = None
        except Exception as exc:
            self.orders_all = []
            self._loading_error = f"Erro ao carregar encomendas: {exc}"
            show_toast(self, self._loading_error, "danger")
        self.orders = self._filtered_orders()
        self.table.setRowCount(len(self.orders))
        for i, row in enumerate(self.orders):
            values = [
                str(row["numero"]),
                str(row["client_nome"]),
                str(row["itens"]),
                str(row["estado"]),
                str(row["tracking"] or "-"),
                "Sim" if int(row["pago"]) else "Não",
                format_currency(float(row["total"])),
            ]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))

        is_empty = not self.orders
        self.table.setVisible(not is_empty)
        self.empty.setVisible(is_empty)
        if is_empty:
            self.selected_order_id = None
            if self._loading_error:
                self.empty.set_content("Erro ao carregar", self._loading_error)
            elif self.search_text or self.status_filter != "todas":
                self.empty.set_content("Sem resultados", "Ajuste os filtros/pesquisa para continuar.")
            else:
                self.empty.set_content("Sem encomendas", "Crie a primeira encomenda para iniciar a operação.")
            self._render_detail(None)
            return

        row_index = 0
        if select_order_id is not None:
            for idx, row in enumerate(self.orders):
                if int(row["id"]) == select_order_id:
                    row_index = idx
                    break
        self.table.selectRow(row_index)

    def _on_selection_changed(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            self.selected_order_id = None
            self._render_detail(None)
            return
        row_index = selected[0].row()
        if row_index >= len(self.orders):
            return
        row = self.orders[row_index]
        self.selected_order_id = int(row["id"])
        self._render_detail(row)

    def _render_detail(self, order: Row | None) -> None:
        self.detail.clear_content()

        if order is None:
            self.detail.add_content_widget(InfoRow("Estado", "Sem encomendas"))
            return

        self.detail.add_content_widget(PanelHeader(str(order["numero"]), str(order["client_nome"])))
        self.detail.add_content_widget(InfoRow("Estado", str(order["estado"])))
        self.detail.add_content_widget(InfoRow("Tracking", str(order["tracking"] or "-")))
        self.detail.add_content_widget(InfoRow("Regra tracking", "Disponível desde pronta_envio"))
        self.detail.add_content_widget(InfoRow("Total", format_currency(float(order["total"]))))

        items = self.order_service.get_order_items(int(order["id"]))
        self.detail.add_content_widget(
            ActivityList(
                "Itens",
                [(f"{item['quantidade']}x", f"{item['nome_snapshot']} · {item['tipo_producao_snapshot']}") for item in items],
            )
        )

        order_state = str(order["estado"])
        can_edit = order_state not in {"expedida", "concluida", "cancelada"}
        can_cancel = str(order["estado"]) != "cancelada"
        can_update_tracking = order_state in TRACKING_ALLOWED_STATES

        edit_btn = PrimaryButton("Editar")
        edit_btn.clicked.connect(self._open_edit)
        edit_btn.setEnabled(can_edit)
        dup_btn = SecondaryButton("Duplicar")
        dup_btn.clicked.connect(self._duplicate_selected)
        cancel_btn = GhostButton("Cancelar")
        cancel_btn.clicked.connect(self._cancel_selected)
        cancel_btn.setEnabled(can_cancel)
        tracking_btn = GhostButton("Atualizar tracking")
        tracking_btn.clicked.connect(self._update_tracking_selected)
        tracking_btn.setEnabled(can_update_tracking)
        if not can_update_tracking:
            tracking_btn.setToolTip("Tracking só pode ser atualizado a partir de pronta_envio")

        self.detail.add_content_widget(Toolbar(edit_btn, dup_btn, tracking_btn, cancel_btn))

    def _open_create(self) -> None:
        dialog = OrderEditorDialog(self.order_service, self.client_service, self.product_service, parent=self)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_order_id=dialog.saved_id)
            show_toast(self, "Encomenda criada", "ok")

    def _open_edit(self) -> None:
        if self.selected_order_id is None:
            return
        order = self.order_service.get_order(self.selected_order_id)
        if order is None:
            show_toast(self, "Encomenda não encontrada", "warning")
            return
        dialog = OrderEditorDialog(self.order_service, self.client_service, self.product_service, dict(order), parent=self)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_order_id=dialog.saved_id)
            show_toast(self, "Encomenda atualizada", "ok")

    def _duplicate_selected(self) -> None:
        if self.selected_order_id is None:
            return
        try:
            new_id = self.order_service.duplicate_order(self.selected_order_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh(select_order_id=new_id)
        show_toast(self, "Encomenda duplicada", "ok")

    def _cancel_selected(self) -> None:
        if self.selected_order_id is None:
            return
        confirm = ConfirmationDialog(
            "Cancelar encomenda",
            "Esta ação é destrutiva. Pretende cancelar a encomenda selecionada?",
            self,
        )
        if not confirm.exec():
            return
        try:
            self.order_service.cancel_order(self.selected_order_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh(select_order_id=self.selected_order_id)
        show_toast(self, "Encomenda cancelada (idempotente)", "warning")

    def _update_tracking_selected(self) -> None:
        if self.selected_order_id is None:
            return
        text, ok = QInputDialog.getText(self, "Tracking", "Novo tracking:")
        if not ok:
            return
        if not text.strip():
            show_toast(self, "Tracking não pode estar vazio", "warning")
            return
        try:
            self.order_service.update_tracking(self.selected_order_id, text)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh(select_order_id=self.selected_order_id)
        show_toast(self, "Tracking atualizado", "info")

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def _set_status_filter(self, value: str) -> None:
        self.status_filter = value
        self.refresh()

    def _export_csv(self) -> None:
        if not self.orders:
            show_toast(self, "Sem resultados para exportar", "warning")
            return
        target, _ = QFileDialog.getSaveFileName(self, "Exportar encomendas", "encomendas.csv", "CSV (*.csv)")
        if not target:
            return
        csv_path = Path(target)
        try:
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "id",
                        "numero",
                        "cliente",
                        "estado",
                        "pago",
                        "tracking",
                        "itens",
                        "subtotal",
                        "portes",
                        "total",
                        "created_at",
                        "updated_at",
                    ]
                )
                for order in self.orders:
                    writer.writerow(
                        [
                            order["id"],
                            order["numero"],
                            order["client_nome"],
                            order["estado"],
                            int(order["pago"]),
                            order["tracking"] or "",
                            order["itens"],
                            float(order["subtotal"]),
                            float(order["portes"]),
                            float(order["total"]),
                            order["created_at"],
                            order["updated_at"],
                        ]
                    )
        except OSError as exc:
            show_toast(self, f"Falha ao exportar CSV: {exc}", "danger")
            return
        show_toast(self, f"Exportado: {csv_path.name}", "ok")

    def _filtered_orders(self) -> list[Row]:
        filtered: list[Row] = []
        for row in self.orders_all:
            if self.status_filter != "todas" and str(row["estado"]) != self.status_filter:
                continue
            if self.search_text:
                haystack = f"{row['numero']} {row['client_nome']} {row['tracking'] or ''} {row['estado']} {row['itens']}".lower()
                if self.search_text not in haystack:
                    continue
            filtered.append(row)
        return filtered
