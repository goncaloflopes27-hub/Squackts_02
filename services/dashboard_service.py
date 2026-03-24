from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from sqlite3 import Row

from repositories.dashboard import DashboardRepository


@dataclass(slots=True)
class DashboardSummary:
    total_orders: int
    total_revenue: Decimal
    total_unpaid: Decimal
    in_production: int
    recent_orders: list[Row]
    production_by_state: dict[str, int]
    alerts: list[str]


class DashboardService:
    def __init__(self, dashboard_repo: DashboardRepository) -> None:
        self.dashboard_repo = dashboard_repo

    def get_summary(self) -> DashboardSummary:
        total_orders = self.dashboard_repo.count_orders()
        total_revenue = self._money(self.dashboard_repo.sum_revenue_non_cancelled())
        total_unpaid = self._money(self.dashboard_repo.sum_unpaid_non_cancelled())
        in_production = self.dashboard_repo.count_in_production()
        recent_orders = self.dashboard_repo.list_recent_orders(limit=8)
        production_rows = self.dashboard_repo.count_production_by_state()
        production_by_state = {str(row["estado"]): int(row["total"]) for row in production_rows}
        alerts = self._build_alerts()

        return DashboardSummary(
            total_orders=total_orders,
            total_revenue=total_revenue,
            total_unpaid=total_unpaid,
            in_production=in_production,
            recent_orders=recent_orders,
            production_by_state=production_by_state,
            alerts=alerts,
        )

    def _build_alerts(self) -> list[str]:
        low_stock = self.dashboard_repo.count_low_stock_products()
        active_queue = self.dashboard_repo.count_active_queue()
        alerts: list[str] = []
        if low_stock > 0:
            alerts.append(f"{low_stock} produtos com stock no mínimo")
        if active_queue > 10:
            alerts.append(f"{active_queue} encomendas em processamento")
        if not alerts:
            alerts.append("Operação estável sem alertas críticos")
        return alerts

    def _money(self, raw: object) -> Decimal:
        return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
