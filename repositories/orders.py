from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class OrderRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def list_all(self) -> list[Row]:
        return self.conn.execute(
            """
            SELECT o.id, o.numero, o.client_id, c.nome AS client_nome, o.estado, o.pago, o.tracking,
                   o.subtotal_cents, o.portes_cents, o.total_cents,
                   o.subtotal_cents / 100.0 AS subtotal,
                   o.portes_cents / 100.0 AS portes,
                   o.total_cents / 100.0 AS total,
                   o.created_at, o.updated_at,
                   (SELECT COALESCE(SUM(quantidade), 0) FROM order_items oi WHERE oi.order_id = o.id) AS itens
            FROM orders o
            JOIN clients c ON c.id = o.client_id
            ORDER BY o.created_at DESC, o.id DESC
            """
        ).fetchall()

    def get_by_id(self, order_id: int) -> Row | None:
        return self.conn.execute(
            """
            SELECT *,
                   subtotal_cents / 100.0 AS subtotal,
                   portes_cents / 100.0 AS portes,
                   total_cents / 100.0 AS total
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()

    def list_items(self, order_id: int) -> list[Row]:
        return self.conn.execute(
            """
            SELECT id, order_id, product_id, sku_snapshot, nome_snapshot, quantidade,
                   preco_unit_cents, custo_unit_cents,
                   preco_unit_cents / 100.0 AS preco_unit,
                   custo_unit_cents / 100.0 AS custo_unit,
                   tipo_producao_snapshot, stock_deducted, stock_returned
            FROM order_items
            WHERE order_id = ?
            ORDER BY id ASC
            """,
            (order_id,),
        ).fetchall()

    def create_order(self, data: dict[str, object]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO orders (numero, client_id, estado, pago, tracking, metodo_pagamento, subtotal_cents, portes_cents, total_cents, data_prevista, notas, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["numero"],
                data["client_id"],
                data["estado"],
                data["pago"],
                data["tracking"],
                data["metodo_pagamento"],
                data["subtotal_cents"],
                data["portes_cents"],
                data["total_cents"],
                data["data_prevista"],
                data["notas"],
                data["created_at"],
                data["updated_at"],
            ),
        )
        return require_lastrowid(cursor, "orders")

    def update_order(self, order_id: int, data: dict[str, object]) -> None:
        self.conn.execute(
            """
            UPDATE orders
            SET client_id = ?, estado = ?, pago = ?, tracking = ?, metodo_pagamento = ?, subtotal_cents = ?,
                portes_cents = ?, total_cents = ?, data_prevista = ?, notas = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["client_id"],
                data["estado"],
                data["pago"],
                data["tracking"],
                data["metodo_pagamento"],
                data["subtotal_cents"],
                data["portes_cents"],
                data["total_cents"],
                data["data_prevista"],
                data["notas"],
                data["updated_at"],
                order_id,
            ),
        )

    def insert_item(self, order_id: int, item: dict[str, object]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO order_items (order_id, product_id, sku_snapshot, nome_snapshot, quantidade, preco_unit_cents, custo_unit_cents,
                                     tipo_producao_snapshot, stock_deducted, stock_returned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                item["product_id"],
                item["sku_snapshot"],
                item["nome_snapshot"],
                item["quantidade"],
                item["preco_unit_cents"],
                item["custo_unit_cents"],
                item["tipo_producao_snapshot"],
                item["stock_deducted"],
                item["stock_returned"],
            ),
        )
        return require_lastrowid(cursor, "orders")

    def delete_items(self, order_id: int) -> None:
        self.conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))

    def mark_item_returned(self, item_id: int) -> None:
        self.conn.execute("UPDATE order_items SET stock_returned = 1 WHERE id = ?", (item_id,))

    def update_state(self, order_id: int, state: str, updated_at: str) -> None:
        self.conn.execute("UPDATE orders SET estado = ?, updated_at = ? WHERE id = ?", (state, updated_at, order_id))

    def update_tracking(self, order_id: int, tracking: str, updated_at: str) -> None:
        self.conn.execute("UPDATE orders SET tracking = ?, updated_at = ? WHERE id = ?", (tracking, updated_at, order_id))

    def get_queue(self, status: str | None = None) -> list[Row]:
        base_sql = """
            SELECT o.id AS order_id, o.numero, o.estado, o.updated_at, c.nome AS client_nome,
                   oi.id AS item_id, oi.product_id, oi.nome_snapshot, oi.quantidade, oi.tipo_producao_snapshot,
                   oi.preco_unit_cents / 100.0 AS preco_unit,
                   oi.stock_deducted, oi.stock_returned
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN clients c ON c.id = o.client_id
        """
        if status is None or status == "todas":
            return self.conn.execute(
                base_sql
                + """
                WHERE o.estado IN ('confirmada', 'paga', 'em_producao', 'pronta_envio')
                ORDER BY o.updated_at DESC, o.id DESC, oi.id DESC
                """
            ).fetchall()
        return self.conn.execute(
            base_sql
            + """
            WHERE o.estado = ?
            ORDER BY o.updated_at DESC, o.id DESC, oi.id DESC
            """,
            (status,),
        ).fetchall()

    def get_max_sequence_for_year(self, year: str) -> int:
        pattern = f"ENC-{year}-%"
        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(CAST(SUBSTR(numero, 10) AS INTEGER)), 0)
            FROM orders
            WHERE numero LIKE ?
            """,
            (pattern,),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0] or 0)
