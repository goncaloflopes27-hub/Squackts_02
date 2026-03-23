from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from sqlite3 import Connection, Row


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
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def get_summary(self) -> DashboardSummary:
        total_orders = int(self.conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
        total_revenue = self._money(self.conn.execute("SELECT COALESCE(SUM(total_cents) / 100.0, 0) FROM orders WHERE estado != 'cancelada'").fetchone()[0])
        total_unpaid = self._money(self.conn.execute("SELECT COALESCE(SUM(total_cents) / 100.0, 0) FROM orders WHERE pago = 0 AND estado != 'cancelada'").fetchone()[0])
        in_production = int(
            self.conn.execute("SELECT COUNT(*) FROM orders WHERE estado IN ('confirmada', 'paga', 'em_producao', 'pronta_envio')").fetchone()[0]
        )
        recent_orders = self.conn.execute(
            """
            SELECT o.numero, o.estado, o.total_cents / 100.0 AS total, o.pago, c.nome AS client_nome, o.updated_at
            FROM orders o
            JOIN clients c ON c.id = o.client_id
            ORDER BY o.id DESC
            LIMIT 8
            """
        ).fetchall()
        production_rows = self.conn.execute(
            """
            SELECT estado, COUNT(*) as total
            FROM orders
            WHERE estado IN ('confirmada', 'paga', 'em_producao', 'pronta_envio')
            GROUP BY estado
            """
        ).fetchall()
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
        low_stock = int(self.conn.execute("SELECT COUNT(*) FROM products WHERE stock <= stock_minimo").fetchone()[0])
        active_queue = int(self.conn.execute("SELECT COUNT(*) FROM orders WHERE estado IN ('confirmada', 'paga', 'em_producao')").fetchone()[0])
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
