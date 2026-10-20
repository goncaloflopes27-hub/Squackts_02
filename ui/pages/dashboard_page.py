from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from services.dashboard_service import DashboardService
from ui.components import (
    DataTable,
    ElevatedCard,
    InfoRow,
    KPIWidget,
    PageHeader,
    PanelHeader,
    SecondaryButton,
    clear_layout,
)
from ui.theme import SPACING
from utils import format_currency


class DashboardPage(QWidget):
    navigate_requested = Signal(str, str)

    def __init__(self, service: DashboardService) -> None:
        super().__init__()
        self.service = service
        self.search_text = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Hoje", "Tudo pronto para um dia bem organizado."))
        self.kpis: list[KPIWidget] = []
        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(SPACING.md)
        root.addLayout(self.kpi_grid)
        lower = QHBoxLayout()
        lower.setSpacing(SPACING.md)
        self.alerts_card = ElevatedCard()
        lower.addWidget(self.alerts_card, stretch=3)
        self.recent_card = ElevatedCard()
        recent_layout = self.recent_card.layout()
        assert recent_layout is not None
        recent_layout.addWidget(PanelHeader("Encomendas recentes", "Pesquisa por número, cliente ou estado"))
        self.recent_table = DataTable(0, 6)
        self.recent_table.setHorizontalHeaderLabels(["Número", "Cliente", "Estado", "Pagamento", "Total", "Atualizada"])
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        recent_layout.addWidget(self.recent_table)
        self.production_card = ElevatedCard("Operação")
        lower.addWidget(self.production_card, stretch=2)
        root.addLayout(lower)
        root.addWidget(self.recent_card)
        self.refresh()

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def refresh(self) -> None:
        summary = self.service.get_summary()

        metrics = [
            ("Valor confirmado", format_currency(summary.total_revenue), "exclui rascunhos e canceladas", "info"),
            (
                "Recebido registado",
                format_currency(summary.total_received),
                "inclui canceladas; ver reembolsos",
                "ok",
            ),
            ("Por receber", format_currency(summary.total_unpaid), "encomendas confirmadas por pagar", "warning"),
            (
                "Prontas para envio",
                str(getattr(summary, "ready_to_ship", 0)),
                "verificar pagamento e tracking",
                "queued",
            ),
        ]
        destinations = ["", "", "", "pronta_envio"]
        for index, (title, value, hint, tone) in enumerate(metrics):
            if index < len(self.kpis):
                self.kpis[index].set_value(value)
            else:
                card = KPIWidget(title, value, hint, tone)
                card.clicked.connect(lambda q=destinations[index]: self.navigate_requested.emit("orders", q))
                self.kpis.append(card)
        self._arrange_kpis()
        alerts_layout = self.alerts_card.layout()
        assert alerts_layout is not None
        clear_layout(alerts_layout)
        alerts_layout.addWidget(PanelHeader("Próximas ações", "Abra a lista para tratar cada pendência"))
        actions = [
            (f"{getattr(summary, 'pending_confirmation', 0)} rascunhos por confirmar", "orders", "rascunho"),
            (f"{summary.in_production} encomendas em produção", "production", ""),
            (f"{getattr(summary, 'ready_to_ship', 0)} prontas para envio", "orders", "pronta_envio"),
            (f"{getattr(summary, 'low_stock_count', 0)} produtos com stock baixo", "products", ""),
        ]
        for label, page, query in actions:
            button = SecondaryButton(label)
            button.clicked.connect(lambda _checked=False, p=page, q=query: self.navigate_requested.emit(p, q))
            alerts_layout.addWidget(button)
        rows = [
            row
            for row in summary.recent_orders
            if not self.search_text
            or self.search_text in f"{row['numero']} {row['client_nome']} {row['estado']}".lower()
        ]
        self.recent_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [
                str(row["numero"]),
                str(row["client_nome"]),
                str(row["estado"]).replace("_", " ").capitalize(),
                "Pago" if int(row["pago"]) else "Pendente",
                format_currency(row["total"]),
                str(row["updated_at"])[:16].replace("T", " "),
            ]
            for j, value in enumerate(values):
                self.recent_table.setItem(i, j, QTableWidgetItem(value))
        layout = self.production_card.layout()
        assert layout is not None
        clear_layout(layout, start_index=1)
        for key, label in [
            ("confirmada", "Por preparar"),
            ("em_producao", "Em produção"),
            ("pronta_envio", "Prontas para envio"),
        ]:
            layout.addWidget(InfoRow(label, str(summary.production_by_state.get(key, 0))))
        layout.addWidget(InfoRow("Unidades por produzir", str(getattr(summary, "production_units", 0))))
        layout.addWidget(InfoRow("Prazos ultrapassados", str(getattr(summary, "overdue_orders", 0))))
        layout.addWidget(InfoRow("Margem estimada", format_currency(getattr(summary, "estimated_margin", 0))))
        layout.addWidget(InfoRow("A reembolsar", format_currency(summary.refunds_pending)))
        layout.addWidget(InfoRow("Reembolsado", format_currency(summary.total_refunded)))
        layout.addWidget(InfoRow("Recebido líquido", format_currency(summary.total_received - summary.total_refunded)))

    def _arrange_kpis(self) -> None:
        columns = 2 if self.width() < 1000 else 4
        for index, card in enumerate(self.kpis):
            self.kpi_grid.addWidget(card, index // columns, index % columns)
        for column in range(4):
            self.kpi_grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._arrange_kpis()
