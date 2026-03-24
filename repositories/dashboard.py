from __future__ import annotations

from sqlite3 import Connection, Row


class DashboardRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def count_orders(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        return int(row[0]) if row is not None else 0

    def sum_revenue_non_cancelled(self) -> float:
        row = self.conn.execute("SELECT COALESCE(SUM(total_cents) / 100.0, 0) FROM orders WHERE estado != 'cancelada'").fetchone()
        return float(row[0]) if row is not None else 0.0

    def sum_unpaid_non_cancelled(self) -> float:
        row = self.conn.execute("SELECT COALESCE(SUM(total_cents) / 100.0, 0) FROM orders WHERE pago = 0 AND estado != 'cancelada'").fetchone()
        return float(row[0]) if row is not None else 0.0

    def count_in_production(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM orders WHERE estado IN ('confirmada', 'paga', 'em_producao', 'pronta_envio')").fetchone()
        return int(row[0]) if row is not None else 0

    def list_recent_orders(self, limit: int = 8) -> list[Row]:
        return self.conn.execute(
            """
            SELECT o.numero, o.estado, o.total_cents / 100.0 AS total, o.pago, c.nome AS client_nome, o.updated_at
            FROM orders o
            JOIN clients c ON c.id = o.client_id
            ORDER BY o.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def count_production_by_state(self) -> list[Row]:
        return self.conn.execute(
            """
            SELECT estado, COUNT(*) as total
            FROM orders
            WHERE estado IN ('confirmada', 'paga', 'em_producao', 'pronta_envio')
            GROUP BY estado
            """
        ).fetchall()

    def count_low_stock_products(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM products WHERE stock <= stock_minimo").fetchone()
        return int(row[0]) if row is not None else 0

    def count_active_queue(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM orders WHERE estado IN ('confirmada', 'paga', 'em_producao')").fetchone()
        return int(row[0]) if row is not None else 0
