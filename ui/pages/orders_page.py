from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Row
from typing import Any

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.client_service import ClientService
from services.image_service import ImageService
from services.order_domain import ORDERED_STATES
from services.order_queries import OrderQuery
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
    def __init__(
        self,
        order_service: OrderService,
        client_service: ClientService,
        product_service: ProductService,
        image_service: ImageService | None = None,
    ) -> None:
        super().__init__()
        self.order_service = order_service
        self.client_service = client_service
        self.product_service = product_service
        self.image_service = image_service
        self.orders: list[Row] = []
        self.orders_all: list[Row] = []
        self.selected_order_id: int | None = None
        self.search_text = ""
        self.status_filter = "todas"
        self._loading_error: str | None = None
        self._page_size = 50
        self._page_offset = 0
        self._total_results = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)

        root.addWidget(PageHeader("Encomendas", "Execução operacional com stock e produção reais."))

        self.new_button = PrimaryButton("Nova encomenda")
        self.new_button.clicked.connect(self._open_create)
        self.search_input = SearchInput("Pesquisar encomenda...")
        self.search_input.textChanged.connect(self.apply_search)
        self.state_combo = QComboBox()
        self.state_combo.addItem("Todos os estados", "todas")
        for state in ORDERED_STATES:
            self.state_combo.addItem(state.replace("_", " ").capitalize(), state)
        self.state_combo.currentIndexChanged.connect(
            lambda _index: self._set_status_filter(str(self.state_combo.currentData()))
        )
        self.payment_filter = QComboBox()
        self.payment_filter.addItems(["Todos os pagamentos", "Por pagar", "Pagas"])
        self.payment_filter.currentIndexChanged.connect(lambda _index: self._filters_changed())
        self.date_filter = QCheckBox("Criadas entre")
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_to = QDateEdit(QDate.currentDate())
        for field in (self.date_from, self.date_to):
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd/MM/yyyy")
            field.setEnabled(False)
            field.dateChanged.connect(lambda _date: self._filters_changed())
        self.date_filter.toggled.connect(self._toggle_dates)
        self.export_button = SecondaryButton("Exportar")
        self.export_button.clicked.connect(self._export_csv)
        root.addWidget(
            Toolbar(self.search_input, self.state_combo, self.payment_filter, self.export_button, self.new_button)
        )
        root.addWidget(Toolbar(self.date_filter, self.date_from, self.date_to))

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
        self.previous_button = SecondaryButton("Anterior")
        self.next_button = SecondaryButton("Seguinte")
        self.page_label = QLabel()
        self.previous_button.clicked.connect(lambda: self._change_page(-1))
        self.next_button.clicked.connect(lambda: self._change_page(1))
        left.addWidget(Toolbar(self.previous_button, self.page_label, self.next_button))
        left_widget = QWidget()
        left_widget.setLayout(left)
        body.addWidget(left_widget, stretch=3)

        self.detail = DetailPanel("Detalhe da encomenda")
        body.addWidget(self.detail, stretch=2)

        root.addLayout(body)
        self.refresh()

    def refresh(self, select_order_id: int | None = None) -> None:
        select_order_id = select_order_id if select_order_id is not None else self.selected_order_id
        scroll = self.table.verticalScrollBar().value()
        self.table.blockSignals(True)
        try:
            result = self.order_service.search_orders(self._query())
            self.orders_all = result.rows
            self._total_results = result.total
            if result.total and self._page_offset >= result.total:
                self._page_offset = ((result.total - 1) // self._page_size) * self._page_size
                self.orders_all = self.order_service.search_orders(self._query()).rows
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
                str(row["estado"]).replace("_", " ").capitalize(),
                str(row["tracking"] or "-"),
                "Sim" if int(row["pago"]) else "Não",
                format_currency(float(row["total"])),
            ]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))

        self.table.blockSignals(False)
        self.previous_button.setEnabled(self._page_offset > 0)
        self.next_button.setEnabled(self._page_offset + self._page_size < self._total_results)
        first = self._page_offset + 1 if self._total_results else 0
        self.page_label.setText(
            f"{first}–{min(self._page_offset + len(self.orders), self._total_results)} de {self._total_results}"
        )
        self.export_button.setEnabled(bool(self.orders))
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
        self.table.blockSignals(True)
        self.table.selectRow(row_index)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll)
        self._on_selection_changed()

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

    def _render_detail(self, order: Row | dict[str, Any] | None) -> None:
        self.detail.clear_content()

        if order is None:
            self.detail.add_content_widget(InfoRow("Estado", "Sem encomendas"))
            return

        full_order = self.order_service.get_order(int(order["id"]))
        order = {**dict(order), **dict(full_order)} if full_order else dict(order)
        self.detail.add_content_widget(PanelHeader(str(order["numero"]), str(order["client_nome"])))
        self.detail.add_content_widget(InfoRow("Estado", str(order["estado"]).replace("_", " ").capitalize()))
        self.detail.add_content_widget(InfoRow("Pagamento", "Pago" if int(order["pago"]) else "Pendente"))
        self.detail.add_content_widget(InfoRow("Data prevista", str(order["data_prevista"]) or "Sem prazo"))
        self.detail.add_content_widget(InfoRow("Notas", str(order["notas"]) or "—"))
        self.detail.add_content_widget(InfoRow("Tracking", str(order["tracking"] or "-")))
        self.detail.add_content_widget(InfoRow("Regra tracking", "Disponível desde pronta_envio"))
        self.detail.add_content_widget(InfoRow("Total", format_currency(float(order["total"]))))

        items = self.order_service.get_order_items(int(order["id"]))
        self.detail.add_content_widget(
            ActivityList(
                "Itens",
                [
                    (f"{item['quantidade']}x", f"{item['nome_snapshot']} · {item['tipo_producao_snapshot']}")
                    for item in items
                ],
            )
        )

        order_state = str(order["estado"])
        allowed = self.order_service.allowed_actions(int(order["id"]))
        can_edit = allowed.can_edit_commercial
        can_cancel = "cancelada" in allowed.targets
        can_update_tracking = allowed.can_update_tracking

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

        self.detail.add_content_widget(Toolbar(edit_btn, dup_btn))
        self.detail.add_content_widget(Toolbar(tracking_btn, cancel_btn))
        payment = SecondaryButton("Marcar por pagar" if int(order["pago"]) else "Registar pagamento")
        payment.clicked.connect(lambda: self._set_payment(not bool(int(order["pago"]))))
        payment.setEnabled(order_state not in {"rascunho", "cancelada", "concluida"})
        if order_state == "rascunho":
            payment.setToolTip("Confirme a encomenda antes de registar o pagamento.")
        self.detail.add_content_widget(payment)
        labels = {
            "confirmada": "Confirmar encomenda",
            "em_producao": "Iniciar produção",
            "pronta_envio": "Marcar pronta para envio",
            "expedida": "Expedir encomenda",
            "concluida": "Concluir encomenda",
        }
        for target in allowed.targets:
            if target not in labels:
                continue
            button = PrimaryButton(labels[target])
            button.clicked.connect(lambda _checked=False, state=target: self._transition(state))
            if target == "expedida" and (not int(order["pago"]) or not str(order["tracking"]).strip()):
                button.setEnabled(False)
                button.setToolTip("Registe o pagamento e o tracking para expedir.")
            self.detail.add_content_widget(button)
        notes = GhostButton("Atualizar notas")
        notes.clicked.connect(self._update_notes)
        self.detail.add_content_widget(notes)
        if order_state == "rascunho":
            reprice = GhostButton("Atualizar preços do catálogo…")
            reprice.clicked.connect(self._reprice)
            self.detail.add_content_widget(reprice)
        history = self.order_service.get_order_history(int(order["id"]))
        self.detail.add_content_widget(
            ActivityList(
                "Atividade",
                [
                    (
                        str(row["acao"]).replace("_", " ").capitalize(),
                        f"{str(row['timestamp'])[:16].replace('T', ' ')} · {row['detalhe'] or ''}",
                    )
                    for row in history
                ]
                or [("Criada", str(order["created_at"]))],
            )
        )

    def _open_create(self) -> None:
        dialog = OrderEditorDialog(
            self.order_service, self.client_service, self.product_service, parent=self, image_service=self.image_service
        )
        if dialog.exec() and dialog.saved_id is not None:
            self._page_offset = 0
            self.refresh(select_order_id=dialog.saved_id)
            show_toast(self, "Encomenda criada", "ok")

    def _open_edit(self) -> None:
        if self.selected_order_id is None:
            return
        order = self.order_service.get_order(self.selected_order_id)
        if order is None:
            show_toast(self, "Encomenda não encontrada", "warning")
            return
        dialog = OrderEditorDialog(
            self.order_service,
            self.client_service,
            self.product_service,
            dict(order),
            parent=self,
            image_service=self.image_service,
        )
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
        self._page_offset = 0
        self.refresh(select_order_id=new_id)
        show_toast(self, "Encomenda duplicada", "ok")

    def _cancel_selected(self) -> None:
        if self.selected_order_id is None:
            return
        confirm = ConfirmationDialog(
            "Cancelar encomenda",
            "Cancelar esta encomenda e devolver o stock reservado?",
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
        show_toast(self, "Encomenda cancelada", "warning")

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
        self._filters_changed()

    def _set_status_filter(self, value: str) -> None:
        self.status_filter = value
        self._page_offset = 0
        index = self.state_combo.findData(value)
        if index >= 0 and self.state_combo.currentIndex() != index:
            self.state_combo.blockSignals(True)
            self.state_combo.setCurrentIndex(index)
            self.state_combo.blockSignals(False)
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
                for order in self._all_filtered_orders():
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

    def _toggle_dates(self, enabled: bool) -> None:
        self.date_from.setEnabled(enabled)
        self.date_to.setEnabled(enabled)
        self._filters_changed()

    def _transition(self, target: str) -> None:
        if self.selected_order_id is None:
            return
        if not ConfirmationDialog(
            "Confirmar ação", f"Alterar a encomenda inteira para {target.replace('_', ' ')}?", self
        ).exec():
            return
        try:
            self.order_service.change_state(self.selected_order_id, target)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()
        show_toast(self, "Encomenda atualizada", "ok")

    def _set_payment(self, paid: bool) -> None:
        if self.selected_order_id is None:
            return
        try:
            self.order_service.set_payment(self.selected_order_id, paid)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()

    def _update_notes(self) -> None:
        if self.selected_order_id is None:
            return
        order = self.order_service.get_order(self.selected_order_id)
        text, ok = QInputDialog.getMultiLineText(
            self, "Notas da encomenda", "Notas:", str(order["notas"]) if order else ""
        )
        if ok:
            try:
                self.order_service.update_notes(self.selected_order_id, text)
            except ValueError as exc:
                show_toast(self, str(exc), "warning")
                return
            self.refresh()

    def _reprice(self) -> None:
        if self.selected_order_id is None:
            return
        current = self.order_service.get_order_items(self.selected_order_id)
        products = {int(p["id"]): p for p in self.product_service.list_products()}
        changes = [
            f"{item['nome_snapshot']}: {format_currency(item['preco_unit'])} → {format_currency(products[int(item['product_id'])]['preco'])}"
            for item in current
            if int(item["product_id"]) in products
        ]
        if not ConfirmationDialog(
            "Rever preços do rascunho", "\n".join(changes) + "\nAplicar os preços atuais do catálogo?", self
        ).exec():
            return
        try:
            self.order_service.reprice_draft(self.selected_order_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()

    def _query(self, *, limit: int | None = None, offset: int | None = None) -> OrderQuery:
        return OrderQuery(
            search=self.search_text,
            state=self.status_filter,
            paid={0: None, 1: False, 2: True}[self.payment_filter.currentIndex()],
            date_from=self.date_from.date().toString("yyyy-MM-dd") if self.date_filter.isChecked() else "",
            date_to=self.date_to.date().toString("yyyy-MM-dd") if self.date_filter.isChecked() else "",
            limit=limit if limit is not None else self._page_size,
            offset=offset if offset is not None else self._page_offset,
        )

    def _all_filtered_orders(self) -> Iterator[Row]:
        offset = 0
        while True:
            result = self.order_service.search_orders(self._query(limit=500, offset=offset))
            yield from result.rows
            offset += len(result.rows)
            if not result.rows or offset >= result.total:
                break

    def _change_page(self, direction: int) -> None:
        self._page_offset = max(0, self._page_offset + direction * self._page_size)
        self.refresh()

    def _filters_changed(self) -> None:
        self._page_offset = 0
        self.refresh()

    def _filtered_orders(self) -> list[Row]:
        return list(self.orders_all)
