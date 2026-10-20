from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from services.production_service import ProductionService
from ui.components import (
    ActivityList,
    ConfirmationDialog,
    DetailPanel,
    EmptyState,
    InfoRow,
    PageHeader,
    PanelHeader,
    PrimaryButton,
    RecordTable,
    SearchInput,
    SecondaryButton,
    Toolbar,
    show_toast,
)
from ui.formatting import display_date
from ui.theme import SPACING


class ProductionPage(QWidget):
    navigate_requested = Signal(str, str)

    def __init__(self, service: ProductionService, inventory_service: Any = None) -> None:
        super().__init__()
        self.service = service
        self.inventory_service = inventory_service
        self.queue: list[dict[str, Any]] = []
        self.selected_order_id: int | None = None
        self.search_text = ""
        self._page_size = 50
        self._page_offset = 0
        self._total_results = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Produção", "Uma linha por encomenda. Arte e qualidade são verificadas por item."))
        self.search_input = SearchInput("Pesquisar encomenda, cliente ou item…")
        self.search_input.textChanged.connect(self.apply_search)
        self.mark_prod = PrimaryButton("Iniciar encomenda")
        self.mark_prod.clicked.connect(
            lambda: self._change(self.service.mark_producing, "Iniciar a produção da encomenda inteira?")
        )
        self.mark_qc = PrimaryButton("Concluir produção e qualidade")
        self.mark_qc.clicked.connect(
            lambda: self._change(
                self.service.mark_produced,
                "Confirma que TODOS os itens estão produzidos e passaram o controlo de qualidade? A ação é bloqueada se existir arte por aprovar.",
            )
        )
        self.mark_ship = SecondaryButton("Ver expedição")
        self.mark_ship.clicked.connect(lambda: self.navigate_requested.emit("orders", "pronta_envio"))
        root.addWidget(Toolbar(self.search_input, self.mark_prod, self.mark_qc, self.mark_ship))
        body = QHBoxLayout()
        self.table = RecordTable(0, 6)
        self.table.setHorizontalHeaderLabels(["Encomenda", "Cliente", "Itens", "Unidades", "Trabalho", "Estado"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection)
        left = QVBoxLayout()
        left.addWidget(self.table)
        self.empty = EmptyState("Fila em dia", "Não há encomendas para preparar ou produzir.")
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
        self.detail = DetailPanel("Encomenda selecionada")
        body.addWidget(self.detail, stretch=2)
        root.addLayout(body)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self.selected_order_id
        scroll = self.table.verticalScrollBar().value()
        groups: dict[int, dict[str, Any]] = {}
        try:
            result = self.service.search_queue(search=self.search_text, limit=self._page_size, offset=self._page_offset)
            rows = result.rows
            self._total_results = result.total
            if result.total and self._page_offset >= result.total:
                self._page_offset = ((result.total - 1) // self._page_size) * self._page_size
                rows = self.service.search_queue(search=self.search_text, limit=self._page_size, offset=self._page_offset).rows
        except (ValueError, OSError) as exc:
            show_toast(self, str(exc), "danger")
            rows = []
        for raw in rows:
            row = dict(raw)
            order_id = int(row["order_id"])
            group = groups.setdefault(order_id, {**row, "items": [], "units": 0})
            group["items"].append(row)
            group["units"] += int(row["quantidade"])
        self.queue = list(groups.values())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.queue))
        for index, order in enumerate(self.queue):
            reserved = sum(int(item.get("reserved_quantity", 0)) for item in order["items"])
            production = sum(int(item.get("production_quantity", 0)) for item in order["items"])
            values = [
                order["numero"],
                order["client_nome"],
                ", ".join(str(item["nome_snapshot"]) for item in order["items"]),
                order["units"],
                f"{reserved} separar · {production} produzir",
                str(order["estado"]).replace("_", " ").capitalize(),
            ]
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(str(value)))
        self.table.blockSignals(False)
        self.previous_button.setEnabled(self._page_offset > 0)
        self.next_button.setEnabled(self._page_offset + self._page_size < self._total_results)
        first = self._page_offset + 1 if self._total_results else 0
        self.page_label.setText(
            f"{first}–{min(self._page_offset + len(self.queue), self._total_results)} de {self._total_results} encomendas"
        )
        self.table.setVisible(bool(self.queue))
        self.empty.setVisible(not self.queue)
        if not self.queue:
            self.selected_order_id = None
            self._render_detail(None)
            self.mark_prod.setEnabled(False)
            self.mark_qc.setEnabled(False)
            return
        target = next((i for i, order in enumerate(self.queue) if int(order["order_id"]) == selected_id), 0)
        self.table.blockSignals(True)
        self.table.selectRow(target)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll)
        self._on_selection()

    def _on_selection(self) -> None:
        selected = self.table.selectedItems()
        if not selected or selected[0].row() >= len(self.queue):
            return
        order = self.queue[selected[0].row()]
        self.selected_order_id = int(order["order_id"])
        state = str(order["estado"])
        tasks = self.inventory_service.list_tasks(int(order["order_id"])) if self.inventory_service else []
        needs_production = bool(tasks) or any(int(item.get("production_quantity", 0)) > 0 for item in order["items"])
        self.mark_prod.setEnabled(state == "confirmada" and needs_production)
        self.mark_qc.setEnabled(state == "em_producao" or (state == "confirmada" and not needs_production))
        self._render_detail(order)

    def _render_detail(self, order: dict[str, Any] | None) -> None:
        self.detail.clear_content()
        if order is None:
            self.detail.add_content_widget(InfoRow("Seleção", "Sem encomenda"))
            return
        self.detail.add_content_widget(PanelHeader(str(order["numero"]), str(order["client_nome"])))
        self.detail.add_content_widget(InfoRow("Âmbito das ações", "Toda a encomenda selecionada"))
        self.detail.add_content_widget(InfoRow("Estado", str(order["estado"]).replace("_", " ").capitalize()))
        self.detail.add_content_widget(InfoRow("Data prevista", display_date(order.get("data_prevista"))))
        self.detail.add_content_widget(
            ActivityList(
                "Itens",
                [
                    (
                        f"{item['quantidade']} unidades",
                        f"{item['nome_snapshot']} · {item.get('reserved_quantity', 0)} reservadas · {item.get('production_quantity', 0)} por produzir",
                    )
                    for item in order["items"]
                ],
            )
        )
        if self.inventory_service:
            for task in self.inventory_service.list_tasks(int(order["order_id"])):
                task = dict(task)
                item_id = int(task["order_item_id"])
                self.detail.add_content_widget(
                    PanelHeader(str(task["nome_snapshot"]), f"{task['quantity']} unidades · {task['status']}")
                )
                if str(task.get("personalization", "")):
                    self.detail.add_content_widget(InfoRow("Personalização", str(task["personalization"])))
                if int(task.get("art_required", 0)):
                    self.detail.add_content_widget(
                        InfoRow("Arte", "Aprovada" if int(task["art_approved"]) else "Por aprovar")
                    )
                    art = SecondaryButton("Aprovar arte deste item")
                    art.setEnabled(not bool(int(task["art_approved"])))
                    art.clicked.connect(lambda _checked=False, item=item_id: self._task_action(item, "art"))
                    self.detail.add_content_widget(art)
                complete = SecondaryButton("Concluir item e aprovar qualidade")
                complete.setEnabled(str(task["status"]) not in {"completed", "concluida", "done"})
                complete.clicked.connect(lambda _checked=False, item=item_id: self._task_action(item, "complete"))
                self.detail.add_content_widget(complete)

    def _task_action(self, item_id: int, action: str) -> None:
        label = (
            "Aprovar a arte selecionada?"
            if action == "art"
            else "Confirmar que este item está produzido e passou o controlo de qualidade?"
        )
        if not ConfirmationDialog("Confirmar item", label, self).exec():
            return
        try:
            if action == "art":
                self.inventory_service.approve_art(item_id)
            else:
                self.inventory_service.complete_task(item_id, qc_passed=True)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()

    def _change(self, action: Callable[[int], None], message: str) -> None:
        if self.selected_order_id is None or not ConfirmationDialog("Confirmar encomenda", message, self).exec():
            return
        try:
            action(self.selected_order_id)
        except ValueError as exc:
            show_toast(self, str(exc), "warning")
            return
        self.refresh()
        show_toast(self, "Encomenda atualizada", "ok")

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self._page_offset = 0
        self.refresh()

    def _change_page(self, direction: int) -> None:
        self._page_offset = max(0, self._page_offset + direction * self._page_size)
        self.refresh()
