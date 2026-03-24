from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from services.dashboard_service import DashboardService
from ui.components import (
    DataTable,
    ElevatedCard,
    InfoRow,
    KPIWidget,
    PageHeader,
    PanelHeader,
    StatusBadge,
    clear_layout,
    show_toast,
)
from ui.theme import SPACING
from utils import format_currency


class DashboardPage(QWidget):
    def __init__(self, service: DashboardService) -> None:
        super().__init__()
        self.service = service
        self.search_text = ""
        self._loading_error: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Painel", "Controlo operacional com dados reais da base de dados."))

        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(SPACING.md)
        root.addLayout(self.kpi_grid)

        lower = QHBoxLayout()
        lower.setSpacing(SPACING.md)

        self.alerts_card = ElevatedCard()
        self.recent_card = ElevatedCard()
        self.recent_table = DataTable(0, 6)
        self.recent_table.setHorizontalHeaderLabels(["Número", "Cliente", "Estado", "Pago", "Total", "Atualizada"])
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        left = QVBoxLayout()
        left.setSpacing(SPACING.md)
        left.addWidget(self.alerts_card)
        left.addWidget(self.recent_card)
        lower.addLayout(left, stretch=3)

        self.production_card = ElevatedCard("Resumo de produção")
        lower.addWidget(self.production_card, stretch=2)
        root.addLayout(lower)

        self.refresh()

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.refresh()

    def refresh(self) -> None:
        try:
            summary = self.service.get_summary()
            self._loading_error = None
        except Exception as exc:
            self._loading_error = f"Falha ao carregar painel: {exc}"
            show_toast(self, self._loading_error, "danger")
            self._render_error_state()
            return

        self._replace_kpis(summary.total_orders, summary.total_revenue, summary.total_unpaid, summary.in_production)
        self._replace_alerts(summary.alerts)
        self._replace_recent(summary.recent_orders)
        self._replace_production(summary.production_by_state)

    def _render_error_state(self) -> None:
        clear_layout(self.kpi_grid, start_index=0)
        self.kpi_grid.addWidget(KPIWidget("Total encomendas", "-", "sem dados", "warning"), 0, 0)
        self.kpi_grid.addWidget(KPIWidget("Total faturado", "-", "sem dados", "warning"), 0, 1)
        self.kpi_grid.addWidget(KPIWidget("Por pagar", "-", "sem dados", "warning"), 0, 2)
        self.kpi_grid.addWidget(KPIWidget("Em produção", "-", "sem dados", "warning"), 0, 3)
        self._replace_alerts([self._loading_error or "Erro desconhecido"])
        self._replace_recent([])
        self._replace_production({})

    def _replace_kpis(self, total_orders: int, total_revenue, total_unpaid, in_production: int) -> None:
        clear_layout(self.kpi_grid, start_index=0)
        self.kpi_grid.addWidget(KPIWidget("Total encomendas", str(total_orders), "real", "info"), 0, 0)
        self.kpi_grid.addWidget(KPIWidget("Total faturado", format_currency(total_revenue), "real", "ok"), 0, 1)
        self.kpi_grid.addWidget(KPIWidget("Por pagar", format_currency(total_unpaid), "atenção", "warning"), 0, 2)
        self.kpi_grid.addWidget(KPIWidget("Em produção", str(in_production), "fila", "queued"), 0, 3)

    def _replace_alerts(self, alerts: list[str]) -> None:
        layout = self.alerts_card.layout()
        clear_layout(layout)
        layout.addWidget(PanelHeader("Alertas simples", "Sinais rápidos para ação diária"))
        for text in alerts:
            row = QHBoxLayout()
            tone = "warning" if "stock" in text.lower() else "info"
            row.addWidget(StatusBadge(text, tone))
            row.addStretch(1)
            holder = QWidget()
            holder.setLayout(row)
            layout.addWidget(holder)

    def _replace_recent(self, rows) -> None:
        filtered_rows = []
        for row in rows:
            if not self.search_text:
                filtered_rows.append(row)
                continue
            haystack = f"{row['numero']} {row['client_nome']} {row['estado']}".lower()
            if self.search_text in haystack:
                filtered_rows.append(row)

        layout = self.recent_card.layout()
        clear_layout(layout)
        layout.addWidget(PanelHeader("Encomendas recentes", "Atualizações mais recentes"))

        self.recent_table.setRowCount(len(filtered_rows))
        for i, row in enumerate(filtered_rows):
            values = [
                str(row["numero"]),
                str(row["client_nome"]),
                str(row["estado"]),
                "Sim" if int(row["pago"]) else "Não",
                format_currency(row["total"]),
                str(row["updated_at"]),
            ]
            for j, value in enumerate(values):
                self.recent_table.setItem(i, j, QTableWidgetItem(value))
        layout.addWidget(self.recent_table)

    def _replace_production(self, production_by_state: dict[str, int]) -> None:
        layout = self.production_card.layout()
        clear_layout(layout, start_index=1)
        for key in ["confirmada", "paga", "em_producao", "pronta_envio"]:
            layout.addWidget(InfoRow(key, str(production_by_state.get(key, 0))))
