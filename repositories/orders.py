from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class OrderRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        # SQLite LIKE folds ASCII only. Names and artwork descriptions must
        # preserve Portuguese and other Unicode case-insensitive searches.
        self.conn.create_function("CASEFOLD", 1, lambda value: str(value or "").casefold(), deterministic=True)

    def list_all(self) -> list[Row]:
        return self.conn.execute(
            """
            SELECT o.*, c.nome AS client_nome,
                   o.subtotal_cents / 100.0 AS subtotal,
                   o.portes_cents / 100.0 AS portes,
                   o.total_cents / 100.0 AS total,
                   (SELECT COALESCE(SUM(quantidade), 0) FROM order_items oi WHERE oi.order_id = o.id) AS itens
            FROM orders o
            JOIN clients c ON c.id = o.client_id
            ORDER BY o.created_at DESC, o.id DESC
            """
        ).fetchall()

    def search_orders(
        self,
        *,
        search: str = "",
        state: str = "todas",
        paid: int | None = None,
        date_from: str = "",
        date_to_exclusive: str = "",
        client_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Row], int]:
        conditions: list[str] = []
        parameters: list[object] = []
        if state != "todas":
            conditions.append("o.estado = ?")
            parameters.append(state)
        if paid is not None:
            conditions.append("o.pago = ?")
            parameters.append(paid)
        if client_id is not None:
            conditions.append("o.client_id = ?")
            parameters.append(client_id)
        if date_from:
            conditions.append("o.created_at >= ?")
            parameters.append(date_from)
        if date_to_exclusive:
            conditions.append("o.created_at < ?")
            parameters.append(date_to_exclusive)
        if search.strip():
            clause, search_parameters = self._text_filter(search)
            conditions.append(clause)
            parameters.extend(search_parameters)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        joined = " FROM orders o JOIN clients c ON c.id = o.client_id "
        count_row = self.conn.execute("SELECT COUNT(*)" + joined + where, parameters).fetchone()
        total = int(count_row[0])
        rows = self.conn.execute(
            """SELECT o.*, c.nome AS client_nome,
                o.subtotal_cents / 100.0 AS subtotal,
                o.portes_cents / 100.0 AS portes,
                o.total_cents / 100.0 AS total,
                (SELECT COALESCE(SUM(quantidade),0) FROM order_items oi WHERE oi.order_id=o.id) AS itens
            """
            + joined
            + where
            + " ORDER BY o.created_at DESC, o.id DESC LIMIT ? OFFSET ?",
            (*parameters, limit, offset),
        ).fetchall()
        return rows, total

    @staticmethod
    def _text_filter(search: str) -> tuple[str, tuple[str, ...]]:
        # LIKE wildcards are escaped separately from SQL parameter binding.
        literal = search.strip().casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{literal}%"
        fields = ("o.numero", "c.nome", "o.estado", "o.tracking", "o.notas")
        direct = " OR ".join("CASEFOLD(" + field + ") LIKE ? ESCAPE '\\'" for field in fields)
        item_clause = """EXISTS (SELECT 1 FROM order_items search_item WHERE search_item.order_id=o.id
            AND (CASEFOLD(search_item.sku_snapshot) LIKE ? ESCAPE '\\'
              OR CASEFOLD(search_item.nome_snapshot) LIKE ? ESCAPE '\\'
              OR CASEFOLD(search_item.personalization) LIKE ? ESCAPE '\\'))"""
        return "(" + direct + " OR " + item_clause + ")", (pattern,) * (len(fields) + 3)

    def search_queue(
        self,
        *,
        status: str = "todas",
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Row], int]:
        conditions = ["EXISTS (SELECT 1 FROM order_items queue_item WHERE queue_item.order_id=o.id)"]
        parameters: list[object] = []
        if status == "todas":
            conditions.append("o.estado IN ('confirmada','em_producao','pronta_envio')")
        else:
            conditions.append("o.estado = ?")
            parameters.append(status)
        if search.strip():
            clause, search_parameters = self._text_filter(search)
            conditions.append(clause)
            parameters.extend(search_parameters)
        matching = " FROM orders o JOIN clients c ON c.id=o.client_id WHERE " + " AND ".join(conditions)
        total = int(self.conn.execute("SELECT COUNT(*)" + matching, parameters).fetchone()[0])
        # Select order IDs first: LIMIT must never split a multi-item order.
        rows = self.conn.execute(
            """WITH selected_orders AS (
                SELECT o.id"""
            + matching
            + """
                ORDER BY o.updated_at DESC, o.id DESC LIMIT ? OFFSET ?
            )
            SELECT oi.*, o.id AS order_id, o.numero, o.estado, o.updated_at, o.data_prevista, o.pago,
                   c.nome AS client_nome, oi.id AS item_id,
                   oi.preco_unit_cents / 100.0 AS preco_unit,
                   COALESCE(a.reserved_quantity,0) AS reserved_quantity,
                   COALESCE(a.production_quantity,0) AS production_quantity,
                   a.status AS allocation_status, t.status AS production_status
            FROM selected_orders selected JOIN orders o ON o.id=selected.id
            JOIN clients c ON c.id=o.client_id
            JOIN order_items oi ON oi.order_id=o.id
            LEFT JOIN inventory_allocations a ON a.order_item_id=oi.id
            LEFT JOIN production_tasks t ON t.order_item_id=oi.id
            ORDER BY o.updated_at DESC, o.id DESC, oi.id DESC
            """,
            (*parameters, limit, offset),
        ).fetchall()
        return rows, total

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
            SELECT oi.*,
                   oi.preco_unit_cents / 100.0 AS preco_unit,
                   oi.custo_unit_cents / 100.0 AS custo_unit,
                   COALESCE(a.reserved_quantity, 0) AS reserved_quantity,
                   COALESCE(a.production_quantity, 0) AS production_quantity,
                   a.status AS allocation_status,
                   t.status AS production_status,
                   COALESCE(t.art_approved, 0) AS art_approved,
                   COALESCE(t.qc_approved, 0) AS qc_approved
            FROM order_items oi
            LEFT JOIN inventory_allocations a ON a.order_item_id = oi.id
            LEFT JOIN production_tasks t ON t.order_item_id = oi.id
            WHERE oi.order_id = ?
            ORDER BY oi.id ASC
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
        columns = [
            "order_id",
            "product_id",
            "sku_snapshot",
            "nome_snapshot",
            "quantidade",
            "preco_unit_cents",
            "custo_unit_cents",
            "tipo_producao_snapshot",
            "stock_deducted",
            "stock_returned",
        ]
        data: dict[str, object] = {**item, "order_id": order_id}
        available = {str(row[1]) for row in self.conn.execute("PRAGMA table_info(order_items)")}
        for key in ("variant_id", "personalization", "artwork_path", "technique_snapshot"):
            if key in available:
                columns.append(key)
                data.setdefault(key, None if key == "variant_id" else "")
        cursor = self.conn.execute(
            "INSERT INTO order_items (" + ", ".join(columns) + ") VALUES (" + ", ".join("?" for _ in columns) + ")",
            tuple(data[column] for column in columns),
        )
        return require_lastrowid(cursor, "orders")

    def update_item(self, item_id: int, quantity: int) -> None:
        self.conn.execute("UPDATE order_items SET quantidade = ? WHERE id = ?", (quantity, item_id))

    def update_item_prices(self, item_id: int, price_cents: int, cost_cents: int) -> None:
        self.conn.execute(
            "UPDATE order_items SET preco_unit_cents = ?, custo_unit_cents = ? WHERE id = ?",
            (price_cents, cost_cents, item_id),
        )

    def delete_item(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM order_items WHERE id = ?", (item_id,))

    def delete_items(self, order_id: int) -> None:
        self.conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))

    def mark_item_returned(self, item_id: int) -> None:
        self.conn.execute("UPDATE order_items SET stock_returned = 1 WHERE id = ?", (item_id,))

    def update_state(self, order_id: int, state: str, updated_at: str) -> None:
        self.conn.execute("UPDATE orders SET estado = ?, updated_at = ? WHERE id = ?", (state, updated_at, order_id))

    def update_tracking(self, order_id: int, tracking: str, updated_at: str) -> None:
        self.conn.execute(
            "UPDATE orders SET tracking = ?, updated_at = ? WHERE id = ?", (tracking, updated_at, order_id)
        )

    def update_payment(self, order_id: int, paid: int, method: str, updated_at: str) -> None:
        self.conn.execute(
            "UPDATE orders SET pago = ?, metodo_pagamento = ?, updated_at = ? WHERE id = ?",
            (paid, method, updated_at, order_id),
        )

    def update_payment_recorded_at(self, order_id: int, recorded_at: str) -> None:
        columns = {str(row[1]) for row in self.conn.execute("PRAGMA table_info(orders)")}
        if "payment_recorded_at" in columns:
            self.conn.execute("UPDATE orders SET payment_recorded_at = ? WHERE id = ?", (recorded_at, order_id))

    def update_notes(self, order_id: int, notes: str, updated_at: str) -> None:
        self.conn.execute("UPDATE orders SET notas = ?, updated_at = ? WHERE id = ?", (notes, updated_at, order_id))

    def update_refund(self, order_id: int, status: str, recorded_at: str, updated_at: str) -> None:
        self.conn.execute(
            "UPDATE orders SET refund_status = ?, refund_recorded_at = ?, updated_at = ? WHERE id = ?",
            (status, recorded_at, updated_at, order_id),
        )

    def get_history(self, order_id: int) -> list[Row]:
        return self.conn.execute(
            """
            SELECT * FROM logs
            WHERE (entidade = 'orders' AND entidade_id = ?)
               OR (entidade = 'order_items' AND entidade_id IN (
                   SELECT CAST(id AS TEXT) FROM order_items WHERE order_id = ?
               ))
            ORDER BY id DESC
            """,
            (str(order_id), order_id),
        ).fetchall()

    def get_queue(self, status: str | None = None) -> list[Row]:
        base_sql = """
            SELECT oi.*, o.id AS order_id, o.numero, o.estado, o.updated_at, o.data_prevista, o.pago,
                   c.nome AS client_nome, oi.id AS item_id,
                   oi.preco_unit_cents / 100.0 AS preco_unit,
                   COALESCE(a.reserved_quantity, 0) AS reserved_quantity,
                   COALESCE(a.production_quantity, 0) AS production_quantity,
                   a.status AS allocation_status, t.status AS production_status
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN clients c ON c.id = o.client_id
            LEFT JOIN inventory_allocations a ON a.order_item_id = oi.id
            LEFT JOIN production_tasks t ON t.order_item_id = oi.id
        """
        if status is None or status == "todas":
            return self.conn.execute(
                base_sql
                + """
                WHERE o.estado IN ('confirmada', 'em_producao', 'pronta_envio')
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
