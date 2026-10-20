from __future__ import annotations

from sqlite3 import Connection, Row


class DashboardRepository:
    """Read-only operational aggregates, with money kept in integer cents."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def totals(self, today: str) -> Row:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total_orders,
                COALESCE(SUM(CASE WHEN estado NOT IN ('rascunho', 'cancelada') THEN total_cents ELSE 0 END), 0) AS ordered_cents,
                COALESCE(SUM(CASE WHEN pago = 1 AND estado NOT IN ('rascunho', 'cancelada') THEN total_cents ELSE 0 END), 0) AS paid_cents,
                COALESCE(SUM(CASE WHEN pago = 0 AND estado NOT IN ('rascunho', 'cancelada') THEN total_cents ELSE 0 END), 0) AS unpaid_cents,
                COALESCE(SUM(CASE WHEN pago = 1 AND estado != 'rascunho' THEN total_cents ELSE 0 END), 0) AS received_cents,
                COALESCE(SUM(CASE WHEN refund_status = 'pending' THEN total_cents ELSE 0 END), 0) AS refund_pending_cents,
                COALESCE(SUM(CASE WHEN refund_status = 'refunded' THEN total_cents ELSE 0 END), 0) AS refunded_cents,
                COALESCE(SUM(CASE WHEN estado = 'em_producao' THEN 1 ELSE 0 END), 0) AS in_production,
                COALESCE(SUM(CASE WHEN estado = 'pronta_envio' THEN 1 ELSE 0 END), 0) AS ready_to_ship,
                COALESCE(SUM(CASE WHEN estado = 'rascunho' THEN 1 ELSE 0 END), 0) AS pending_confirmation,
                COALESCE(SUM(CASE WHEN data_prevista != '' AND substr(data_prevista, 1, 10) < ?
                    AND estado NOT IN ('rascunho', 'cancelada', 'expedida', 'concluida') THEN 1 ELSE 0 END), 0) AS overdue_orders
            FROM orders
            """,
            (today,),
        ).fetchone()
        assert row is not None
        return row

    def recent_orders(self, limit: int = 8) -> list[Row]:
        return self.conn.execute(
            """
            SELECT o.id, o.numero, o.estado, o.total_cents, o.total_cents / 100.0 AS total,
                   o.pago, c.nome AS client_nome, o.updated_at, o.data_prevista
            FROM orders o JOIN clients c ON c.id = o.client_id
            ORDER BY o.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def production_counts(self) -> list[Row]:
        return self.conn.execute(
            """SELECT estado, COUNT(*) AS total FROM orders
               WHERE estado IN ('confirmada', 'em_producao', 'pronta_envio') GROUP BY estado"""
        ).fetchall()

    def low_stock_count(self) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) FROM products
               WHERE ativo = 1 AND tipo_producao IN ('stock_fisico', 'misto') AND stock <= stock_minimo"""
        ).fetchone()
        return int(row[0])

    def estimated_margin_cents(self) -> int:
        row = self.conn.execute(
            """SELECT COALESCE(SUM((i.preco_unit_cents - i.custo_unit_cents) * i.quantidade), 0)
               FROM order_items i JOIN orders o ON o.id = i.order_id
               WHERE o.estado NOT IN ('rascunho', 'cancelada')"""
        ).fetchone()
        return int(row[0])

    def production_units(self) -> int:
        row = self.conn.execute(
            """SELECT COALESCE(SUM(t.quantity), 0)
               FROM production_tasks t JOIN order_items i ON i.id = t.order_item_id
               JOIN orders o ON o.id = i.order_id
               WHERE o.estado IN ('confirmada', 'em_producao') AND t.status != 'concluida'"""
        ).fetchone()
        return int(row[0])
