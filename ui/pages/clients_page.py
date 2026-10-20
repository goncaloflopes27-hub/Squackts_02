from __future__ import annotations

import csv
from pathlib import Path
from sqlite3 import Row

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from services.client_service import ClientService
from services.image_service import ImageService
from services.order_queries import OrderQuery
from services.order_service import OrderService
from services.product_service import ProductService
from ui.components import (
    ActivityList,
    ConfirmationDialog,
    DetailPanel,
    EmptyState,
    InfoRow,
    MetricTile,
    PageHeader,
    PanelHeader,
    PrimaryButton,
    RecordTable,
    SearchInput,
    SecondaryButton,
    Toolbar,
    show_toast,
)
from ui.dialogs import ClientEditorDialog, OrderEditorDialog
from ui.theme import SPACING
from utils import format_currency


class ClientsPage(QWidget):
    def __init__(
        self,
        service: ClientService,
        order_service: OrderService | None = None,
        product_service: ProductService | None = None,
        image_service: ImageService | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.order_service = order_service
        self.product_service = product_service
        self.image_service = image_service
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
        root.addWidget(PageHeader("Clientes", "Pessoas, contactos e o histórico de cada encomenda."))
        self.search_input = SearchInput("Pesquisar cliente por nome, email ou telefone...")
        self.search_input.textChanged.connect(self.apply_search)
        self.active_combo = QComboBox()
        self.active_combo.addItems(["Ativos", "Arquivados", "Todos"])
        self.active_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.export_button = SecondaryButton("Exportar CSV")
        self.export_button.clicked.connect(self._export_csv)
        root.addWidget(Toolbar(self.search_input, self.active_combo, self.export_button, new_button))

        self.metrics_layout = QHBoxLayout()
        self.metric_total = MetricTile("Clientes na lista", "0")
        self.metric_emails = MetricTile("Com email", "0")
        self.metric_nif = MetricTile("Com NIF", "0")
        self.metrics_layout.addWidget(self.metric_total)
        self.metrics_layout.addWidget(self.metric_emails)
        self.metrics_layout.addWidget(self.metric_nif)
        root.addLayout(self.metrics_layout)

        split = QHBoxLayout()
        split.setSpacing(SPACING.md)

        self.table = RecordTable(0, 5)
        self.table.setHorizontalHeaderLabels(["Cliente", "Email", "Telefone", "NIF", "Morada"])
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
        select_client_id = select_client_id if select_client_id is not None else self.selected_client_id
        scroll = self.table.verticalScrollBar().value()
        self.table.blockSignals(True)
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
            values = [str(row["nome"]), email, str(row["telefone"]), nif, str(row["morada"])]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))

        self.metric_total.set_value(str(len(self.clients)))
        self.metric_emails.set_value(str(with_email))
        self.metric_nif.set_value(str(with_nif))

        self.table.blockSignals(False)
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
        self.table.blockSignals(True)
        self.table.selectRow(target_row)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll)
        self._on_selection_changed()

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def _filtered_clients(self) -> list[Row]:
        rows = list(self.clients_all)
        if self.active_combo.currentIndex() != 2:
            active = self.active_combo.currentIndex() == 0
            rows = [row for row in rows if bool(int(row["ativo"])) == active]
        if not self.search_text:
            return rows
        filtered: list[Row] = []
        for row in rows:
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
                writer.writerow(
                    ["id", "nome", "email", "telefone", "nif", "morada", "ativo", "created_at", "updated_at"]
                )
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
            return
        row = selected_items[0].row()
        if row >= len(self.clients):
            return
        client = self.clients[row]
        self.selected_client_id = int(client["id"])
        self._render_detail(client)

    def _render_detail(self, client: Row | None) -> None:
        self.detail.clear_content()

        if client is None:
            self.detail.add_content_widget(InfoRow("Estado", "Sem seleção"))
            return

        self.detail.add_content_widget(PanelHeader(str(client["nome"]), str(client["email"])))
        self.detail.add_content_widget(InfoRow("Telefone", str(client["telefone"]) or "-"))
        self.detail.add_content_widget(InfoRow("NIF", str(client["nif"]) or "-"))
        self.detail.add_content_widget(InfoRow("Morada", str(client["morada"]) or "-"))
        self.detail.add_content_widget(InfoRow("Notas", str(client["notas"]) or "-"))

        edit_button = PrimaryButton("Editar cliente")
        edit_button.clicked.connect(self._open_edit)
        self.detail.add_content_widget(edit_button)
        if int(client["ativo"]):
            create = PrimaryButton("Nova encomenda para este cliente")
            create.setEnabled(self.order_service is not None and self.product_service is not None)
            create.clicked.connect(self._create_order)
            self.detail.add_content_widget(create)
            archive = SecondaryButton("Arquivar cliente")
            archive.clicked.connect(self._archive_selected)
            self.detail.add_content_widget(archive)
        if self.order_service:
            result = self.order_service.search_orders(OrderQuery(client_id=int(client["id"]), limit=20))
            orders = result.rows
            self.detail.add_content_widget(InfoRow("Encomendas", str(result.total)))
            self.detail.add_content_widget(
                ActivityList(
                    "Encomendas recentes (até 20)",
                    [
                        (
                            str(order["numero"]),
                            f"{str(order['estado']).replace('_', ' ')} · {format_currency(order['total'])}",
                        )
                        for order in orders
                    ]
                    or [("Sem encomendas", "Este cliente ainda não tem encomendas.")],
                )
            )

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

    def _create_order(self) -> None:
        if self.selected_client_id is None or self.order_service is None or self.product_service is None:
            return
        dialog = OrderEditorDialog(
            self.order_service,
            self.service,
            self.product_service,
            parent=self,
            initial_client_id=self.selected_client_id,
            image_service=self.image_service,
        )
        if dialog.exec():
            self.refresh()
            show_toast(self, "Encomenda criada", "ok")

    def _archive_selected(self) -> None:
        if self.selected_client_id is None:
            return
        if not ConfirmationDialog(
            "Arquivar cliente", "Retirar este cliente das novas encomendas, preservando o histórico?", self
        ).exec():
            return
        try:
            self.service.archive_client(self.selected_client_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()
        show_toast(self, "Cliente arquivado", "ok")
