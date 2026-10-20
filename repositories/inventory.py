from __future__ import annotations

from sqlite3 import Connection, Row


class InventoryRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def list_order_items(self, order_id: int) -> list[Row]:
        return self.conn.execute(
            "SELECT oi.*,o.estado FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.order_id=? ORDER BY oi.id",
            (order_id,),
        ).fetchall()

    def get_item(self, item_id: int) -> Row | None:
        return self.conn.execute(
            "SELECT oi.*,o.estado FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.id=?", (item_id,)
        ).fetchone()

    def get_allocation(self, item_id: int) -> Row | None:
        return self.conn.execute("SELECT * FROM inventory_allocations WHERE order_item_id=?", (item_id,)).fetchone()

    def save_allocation(self, item_id: int, variant_id: int, reserved: int, production: int, now: str) -> None:
        self.conn.execute(
            """INSERT INTO inventory_allocations
            (order_item_id,variant_id,reserved_quantity,production_quantity,status,created_at,updated_at)
            VALUES (?,?,?,?,'reserved',?,?) ON CONFLICT(order_item_id) DO UPDATE SET
            variant_id=excluded.variant_id,reserved_quantity=excluded.reserved_quantity,
            production_quantity=excluded.production_quantity,status='reserved',updated_at=excluded.updated_at""",
            (item_id, variant_id, reserved, production, now, now),
        )
        self.conn.execute("UPDATE order_items SET variant_id=?,stock_returned=0 WHERE id=?", (variant_id, item_id))

    def set_status(self, item_id: int, status: str, now: str) -> None:
        self.conn.execute(
            "UPDATE inventory_allocations SET status=?,updated_at=? WHERE order_item_id=?", (status, now, item_id)
        )
        if status == "released":
            self.conn.execute("UPDATE order_items SET stock_returned=1 WHERE id=?", (item_id,))
        elif status == "consumed":
            self.conn.execute(
                "UPDATE order_items SET stock_deducted=CASE WHEN (SELECT reserved_quantity FROM inventory_allocations WHERE order_item_id=?)>0 THEN 1 ELSE 0 END,stock_returned=0 WHERE id=?",
                (item_id, item_id),
            )

    def movement(
        self,
        variant_id: int,
        kind: str,
        physical_delta: int,
        reserved_delta: int,
        reason: str,
        now: str,
        order_id: int | None = None,
        item_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO inventory_movements
            (variant_id,order_id,order_item_id,kind,on_hand_delta,reserved_delta,reason,created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (variant_id, order_id, item_id, kind, physical_delta, reserved_delta, reason, now),
        )

    def list_movements(self, variant_id: int | None = None, limit: int = 200) -> list[Row]:
        return self.conn.execute(
            """SELECT m.*,v.sku FROM inventory_movements m JOIN product_variants v ON v.id=m.variant_id
            WHERE (? IS NULL OR m.variant_id=?) ORDER BY m.id DESC LIMIT ?""",
            (variant_id, variant_id, limit),
        ).fetchall()
