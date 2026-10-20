from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from sqlite3 import Connection, Row

from repositories.dashboard import DashboardRepository
from utils import cents_to_money


@dataclass(slots=True)
class DashboardSummary:
    total_orders: int
    total_revenue: Decimal
    total_unpaid: Decimal
    in_production: int
    recent_orders: list[Row]
    production_by_state: dict[str, int]
    alerts: list[str]
    total_paid: Decimal = Decimal("0.00")
    ready_to_ship: int = 0
    overdue_orders: int = 0
    pending_confirmation: int = 0
    estimated_margin: Decimal = Decimal("0.00")
    low_stock_count: int = 0
    production_units: int = 0
    total_received: Decimal = Decimal("0.00")
    refunds_pending: Decimal = Decimal("0.00")
    total_refunded: Decimal = Decimal("0.00")


class DashboardService:
    def __init__(self, conn: Connection, repository: DashboardRepository | None = None) -> None:
        self.repository = repository or DashboardRepository(conn)

    def get_summary(self) -> DashboardSummary:
        totals = self.repository.totals(date.today().isoformat())
        counts = {str(row["estado"]): int(row["total"]) for row in self.repository.production_counts()}
        low_stock = self.repository.low_stock_count()
        alerts: list[str] = []
        if int(totals["overdue_orders"]):
            alerts.append(f"{totals['overdue_orders']} encomendas com prazo ultrapassado")
        if int(totals["ready_to_ship"]):
            alerts.append(f"{totals['ready_to_ship']} encomendas prontas para envio")
        if int(totals["pending_confirmation"]):
            alerts.append(f"{totals['pending_confirmation']} rascunhos por confirmar")
        if low_stock:
            alerts.append(f"{low_stock} produtos com stock disponível no mínimo")
        if not alerts:
            alerts.append("Operação estável sem pendências críticas")
        return DashboardSummary(
            total_orders=int(totals["total_orders"]),
            total_revenue=cents_to_money(totals["ordered_cents"]),
            total_unpaid=cents_to_money(totals["unpaid_cents"]),
            in_production=int(totals["in_production"]),
            recent_orders=self.repository.recent_orders(),
            production_by_state=counts,
            alerts=alerts,
            total_paid=cents_to_money(totals["paid_cents"]),
            ready_to_ship=int(totals["ready_to_ship"]),
            overdue_orders=int(totals["overdue_orders"]),
            pending_confirmation=int(totals["pending_confirmation"]),
            estimated_margin=cents_to_money(self.repository.estimated_margin_cents()),
            low_stock_count=low_stock,
            production_units=self.repository.production_units(),
            total_received=cents_to_money(totals["received_cents"]),
            refunds_pending=cents_to_money(totals["refund_pending_cents"]),
            total_refunded=cents_to_money(totals["refunded_cents"]),
        )
