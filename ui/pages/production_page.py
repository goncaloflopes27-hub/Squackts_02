from __future__ import annotations

from collections.abc import Callable
from sqlite3 import Row

from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from services.production_service import ProductionService
from ui.components import (
    ConfirmationDialog,
    DataTable,
    DetailPanel,
    EmptyState,
    InfoRow,
    PageHeader,
    PanelHeader,
    PrimaryButton,
    SearchInput,
    SegmentedControl,
    StatusBadge,
    Toolbar,
    show_toast,
)
from ui.theme import SPACING
from utils import format_currency


class ProductionPage(QWidget):
    def __init__(self, service: ProductionService) -> None:
        super().__init__()
        self.service = service
        self.queue: list[Row] = []
        self.queue_all: list[Row] = []
        self.selected_order_id: int | None = None
        self.current_filter = "todas"
        self.search_text = ""
        self._loading_error: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Produção", "Fila operacional com transições seguras de estado."))

        self.segment = SegmentedControl(["todas", "confirmada", "paga", "em_producao", "pronta_envio"])
        self.segment.selection_changed.connect(self._set_filter)
        self.search_input = SearchInput("Pesquisar pedido, cliente, item ou estado...")
        self.search_input.textChanged.connect(self.apply_search)
        root.addWidget(Toolbar(self.search_input, self.segment))

        body = QHBoxLayout()
        body.setSpacing(SPACING.md)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)

        actions = QHBoxLayout()
        actions.addWidget(PanelHeader("Fila real", "Ações por encomenda selecionada"))
        actions.addStretch(1)
        self.mark_prod = PrimaryButton("Marcar produção")
        self.mark_prod.clicked.connect(self._mark_producing)
        self.mark_qc = PrimaryButton("Marcar pronta envio")
        self.mark_qc.clicked.connect(self._mark_produced)
        self.mark_ship = PrimaryButton("Marcar expedida")
        self.mark_ship.clicked.connect(self._mark_shipped)
        actions.addWidget(self.mark_prod)
        actions.addWidget(self.mark_qc)
        actions.addWidget(self.mark_ship)
        actions_widget = QWidget()
        actions_widget.setLayout(actions)
        left.addWidget(actions_widget)

        self.table = DataTable(0, 8)
        self.table.setHorizontalHeaderLabels(["Pedido", "Cliente", "Item", "Qtd", "Tipo", "Estado", "Stock deduzido", "Devolvido"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection)
        left.addWidget(self.table)

        self.empty = EmptyState("Sem itens de produção", "Não há itens para o filtro/pesquisa atual.")
        left.addWidget(self.empty)

        left_widget = QWidget()
        left_widget.setLayout(left)
        body.addWidget(left_widget, stretch=3)

        self.detail = DetailPanel("Detalhe da seleção")
        body.addWidget(self.detail, stretch=2)

        root.addLayout(body)
        self.refresh()

    def _set_filter(self, value: str) -> None:
        self.current_filter = value
        self.segment.set_value(value)
        self.refresh()

    def refresh(self) -> None:
        try:
            self.queue_all = self.service.get_production_queue(self.current_filter)
            self._loading_error = None
        except Exception as exc:
            self.queue_all = []
            self._loading_error = f"Erro ao carregar fila de produção: {exc}"
            show_toast(self, self._loading_error, "danger")
        self.queue = self._filtered_queue()
        self.table.setRowCount(len(self.queue))
        for i, row in enumerate(self.queue):
            values = [
                str(row["numero"]),
                str(row["client_nome"]),
                str(row["nome_snapshot"]),
                str(row["quantidade"]),
                str(row["tipo_producao_snapshot"]),
                str(row["estado"]),
                "Sim" if int(row["stock_deducted"]) else "Não",
                "Sim" if int(row["stock_returned"]) else "Não",
            ]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))

        is_empty = len(self.queue) == 0
        self.table.setVisible(not is_empty)
        self.empty.setVisible(is_empty)
        if is_empty:
            self.selected_order_id = None
            if self._loading_error:
                self.empty.set_content("Erro ao carregar", self._loading_error)
            else:
                self.empty.set_content("Sem itens de produção", "Não há itens para o filtro/pesquisa atual.")
            self._render_detail(None)
            self._update_action_states(None)
            return
        self.table.selectRow(0)

    def _on_selection(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            self.selected_order_id = None
            self._render_detail(None)
            self._update_action_states(None)
            return
        row_index = selected[0].row()
        if row_index >= len(self.queue):
            return
        row = self.queue[row_index]
        self.selected_order_id = int(row["order_id"])
        self._render_detail(row)
        self._update_action_states(str(row["estado"]))

    def _render_detail(self, row: Row | None) -> None:
        self.detail.clear_content()

        if row is None:
            self.detail.add_content_widget(InfoRow("Estado", "Sem seleção"))
            return

        self.detail.add_content_widget(PanelHeader(str(row["numero"]), str(row["client_nome"])))
        self.detail.add_content_widget(InfoRow("Estado", str(row["estado"])))
        self.detail.add_content_widget(InfoRow("Item", str(row["nome_snapshot"])))
        self.detail.add_content_widget(InfoRow("Quantidade", str(row["quantidade"])))
        self.detail.add_content_widget(InfoRow("Preço unit", format_currency(row["preco_unit"])))
        self.detail.add_content_widget(InfoRow("Atualizado", str(row["updated_at"])))

        tone = "info"
        state = str(row["estado"])
        if state == "em_producao":
            tone = "queued"
        elif state in {"pronta_envio", "expedida"}:
            tone = "ok"
        elif state == "confirmada":
            tone = "warning"
        self.detail.add_content_widget(StatusBadge(f"Estado: {state}", tone))

    def _update_action_states(self, state: str | None) -> None:
        self.mark_prod.setEnabled(state in {"confirmada", "paga"})
        self.mark_qc.setEnabled(state == "em_producao")
        self.mark_ship.setEnabled(state == "pronta_envio")

    def _mark_producing(self) -> None:
        self._confirm_and_change("em_producao", self.service.mark_producing)

    def _mark_produced(self) -> None:
        self._confirm_and_change("pronta_envio", self.service.mark_produced)

    def _mark_shipped(self) -> None:
        self._confirm_and_change("expedida", self.service.mark_shipped)

    def _confirm_and_change(self, new_state: str, action: Callable[[int], None]) -> None:
        if self.selected_order_id is None:
            show_toast(self, "Selecione uma encomenda", "warning")
            return
        confirm = ConfirmationDialog("Confirmar transição", f"Pretende mudar o estado para '{new_state}'?", self)
        if not confirm.exec():
            return
        try:
            action(self.selected_order_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()
        show_toast(self, f"Estado -> {new_state}", "ok")

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def _filtered_queue(self) -> list[Row]:
        if not self.search_text:
            return list(self.queue_all)
        result: list[Row] = []
        for row in self.queue_all:
            haystack = f"{row['estado']} {row['numero']} {row['client_nome']} {row['nome_snapshot']}".lower()
            if self.search_text in haystack:
                result.append(row)
        return result
