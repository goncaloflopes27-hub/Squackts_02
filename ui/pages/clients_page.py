from __future__ import annotations

import csv
from pathlib import Path
from sqlite3 import Row

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from services.client_service import ClientService
from services.order_service import OrderService
from ui.components import (
    ActivityList,
    DataTable,
    DetailPanel,
    EmptyState,
    InfoRow,
    MetricTile,
    PageHeader,
    PanelHeader,
    PrimaryButton,
    SearchInput,
    Toolbar,
    show_toast,
)
from ui.dialogs import ClientEditorDialog
from ui.theme import SPACING
from utils import format_currency


class ClientsPage(QWidget):
    def __init__(self, service: ClientService, order_service: OrderService) -> None:
        super().__init__()
        self.service = service
        self.order_service = order_service
        self.clients: list[Row] = []
        self.clients_all: list[Row] = []
        self.selected_client_id: int | None = None
        self.search_text = ""
        self._loading_error: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)

        new_button = PrimaryButton("Novo cliente")
        new_button.clicked.connect(self._open_create)
        root.addWidget(PageHeader("Clientes", "Dados pessoais e comerciais com contexto de relacionamento."))
        self.search_input = SearchInput("Pesquisar cliente por nome, email ou telefone...")
        self.search_input.textChanged.connect(self.apply_search)
        self.export_button = PrimaryButton("Exportar CSV")
        self.export_button.clicked.connect(self._export_csv)
        root.addWidget(Toolbar(self.search_input, self.export_button, new_button))

        self.metrics_layout = QHBoxLayout()
        self.metric_total = MetricTile("Clientes ativos", "0")
        self.metric_emails = MetricTile("Com email", "0")
        self.metric_nif = MetricTile("Com NIF", "0")
        self.metrics_layout.addWidget(self.metric_total)
        self.metrics_layout.addWidget(self.metric_emails)
        self.metrics_layout.addWidget(self.metric_nif)
        root.addLayout(self.metrics_layout)

        split = QHBoxLayout()
        split.setSpacing(SPACING.md)

        self.table = DataTable(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Cliente", "Email", "Telefone", "NIF", "Morada"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.empty = EmptyState("Sem clientes", "Crie o primeiro cliente para começar.")

        list_wrap = QVBoxLayout()
        list_wrap.setContentsMargins(0, 0, 0, 0)
        list_wrap.addWidget(self.table)
        list_wrap.addWidget(self.empty)
        list_widget = QWidget()
        list_widget.setLayout(list_wrap)
        split.addWidget(list_widget, stretch=3)

        self.detail = DetailPanel("Perfil do cliente")
        self.detail.add_content_widget(PanelHeader("Nenhum cliente", "Selecione um item"))
        split.addWidget(self.detail, stretch=2)

        root.addLayout(split)
        self.refresh()

    def refresh(self, select_client_id: int | None = None) -> None:
        try:
            self.clients_all = self.service.list_clients()
            self._loading_error = None
        except Exception as exc:
            self.clients_all = []
            self._loading_error = f"Erro ao carregar clientes: {exc}"
            show_toast(self, self._loading_error, "danger")
        self.clients = self._filtered_clients()
        self.table.setRowCount(len(self.clients))

        with_email = 0
        with_nif = 0
        for i, row in enumerate(self.clients):
            email = str(row["email"])
            nif = str(row["nif"])
            with_email += 1 if email else 0
            with_nif += 1 if nif else 0
            values = [str(row["id"]), str(row["nome"]), email, str(row["telefone"]), nif, str(row["morada"])]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))

        self.metric_total.set_value(str(len(self.clients)))
        self.metric_emails.set_value(str(with_email))
        self.metric_nif.set_value(str(with_nif))

        is_empty = len(self.clients) == 0
        self.table.setVisible(not is_empty)
        self.empty.setVisible(is_empty)
        self.export_button.setEnabled(not is_empty)

        if is_empty:
            self.selected_client_id = None
            if self._loading_error:
                self.empty.set_content("Erro ao carregar", self._loading_error)
            elif self.search_text:
                self.empty.set_content("Sem resultados", "Refine a pesquisa para encontrar clientes.")
            else:
                self.empty.set_content("Sem clientes", "Crie o primeiro cliente para começar.")
            self._render_detail(None)
            return

        target_row = 0
        if select_client_id is not None:
            for idx, client in enumerate(self.clients):
                if int(client["id"]) == select_client_id:
                    target_row = idx
                    break
        self.table.selectRow(target_row)

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def _filtered_clients(self) -> list[Row]:
        if not self.search_text:
            return list(self.clients_all)
        filtered: list[Row] = []
        for row in self.clients_all:
            haystack = f"{row['nome']} {row['email']} {row['telefone']} {row['nif']} {row['morada']}".lower()
            if self.search_text in haystack:
                filtered.append(row)
        return filtered

    def _export_csv(self) -> None:
        if not self.clients:
            show_toast(self, "Sem clientes para exportar", "warning")
            return
        target, _ = QFileDialog.getSaveFileName(self, "Exportar clientes", "clientes.csv", "CSV (*.csv)")
        if not target:
            return
        csv_path = Path(target)
        try:
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["id", "nome", "email", "telefone", "nif", "morada", "ativo", "created_at", "updated_at"])
                for row in self.clients:
                    writer.writerow(
                        [
                            row["id"],
                            row["nome"],
                            row["email"],
                            row["telefone"],
                            row["nif"],
                            row["morada"],
                            int(row["ativo"]),
                            row["created_at"],
                            row["updated_at"],
                        ]
                    )
        except OSError as exc:
            show_toast(self, f"Falha ao exportar clientes: {exc}", "danger")
            return
        show_toast(self, f"Clientes exportados: {csv_path.name}", "ok")

    def _on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.selected_client_id = None
            self._render_detail(None)
            return
        row = selected_items[0].row()
        if row >= len(self.clients):
            self.selected_client_id = None
            self._render_detail(None)
            return
        client = self.clients[row]
        self.selected_client_id = int(client["id"])
        self._render_detail(client)

    def _render_detail(self, client: Row | None) -> None:
        self.detail.clear_content()

        if client is None:
            self.detail.add_content_widget(InfoRow("Estado", "Sem seleção"))
            return

        email = str(client["email"]) or "Sem email"
        self.detail.add_content_widget(PanelHeader(str(client["nome"]), email))
        self.detail.add_content_widget(InfoRow("ID interno", str(client["id"])))
        self.detail.add_content_widget(InfoRow("Telefone", str(client["telefone"]) or "-"))
        self.detail.add_content_widget(InfoRow("NIF", str(client["nif"]) or "-"))
        self.detail.add_content_widget(InfoRow("Morada", str(client["morada"]) or "-"))
        self.detail.add_content_widget(InfoRow("Notas", str(client["notas"]) or "-"))
        self._add_orders_history(client)

        edit_button = PrimaryButton("Editar cliente")
        edit_button.clicked.connect(self._open_edit)
        self.detail.add_content_widget(edit_button)

    def _open_create(self) -> None:
        dialog = ClientEditorDialog(self.service, parent=self)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_client_id=dialog.saved_id)
            show_toast(self, "Cliente criado", "ok")

    def _open_edit(self) -> None:
        if self.selected_client_id is None:
            return
        row = self.service.get_client(self.selected_client_id)
        if row is None:
            show_toast(self, "Cliente não encontrado", "warning")
            return
        dialog = ClientEditorDialog(self.service, client=dict(row), parent=self)
        if dialog.exec() and dialog.saved_id is not None:
            self.refresh(select_client_id=dialog.saved_id)
            show_toast(self, "Cliente atualizado", "ok")

    def _add_orders_history(self, client: Row) -> None:
        client_id = int(client["id"])
        orders = self.order_service.list_orders_for_client(client_id)
        if not orders:
            self.detail.add_content_widget(InfoRow("Histórico", "Sem encomendas associadas"))
            return
        total_value = sum(float(order["total"]) for order in orders)
        self.detail.add_content_widget(InfoRow("Encomendas", str(len(orders))))
        self.detail.add_content_widget(InfoRow("Total faturado", format_currency(total_value)))
        recent_rows = [(str(order["numero"]), f"{order['estado']} · {format_currency(float(order['total']))}") for order in orders[:5]]
        self.detail.add_content_widget(ActivityList("Histórico recente", recent_rows))
