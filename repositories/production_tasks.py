from __future__ import annotations

from sqlite3 import Connection, Row


class ProductionTaskRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def get_for_item(self, item_id: int) -> Row | None:
        return self.conn.execute("SELECT * FROM production_tasks WHERE order_item_id=?", (item_id,)).fetchone()

    def list_for_order(self, order_id: int) -> list[Row]:
        return self.conn.execute(
            """SELECT t.*,oi.order_id,oi.nome_snapshot,oi.sku_snapshot,oi.personalization,oi.artwork_path
            FROM production_tasks t JOIN order_items oi ON oi.id=t.order_item_id
            WHERE oi.order_id=? ORDER BY t.id""",
            (order_id,),
        ).fetchall()

    def ensure(self, item_id: int, quantity: int, technique: str, art_reference: str, now: str) -> None:
        self.conn.execute(
            """INSERT INTO production_tasks
            (order_item_id,quantity,technique,art_required,artwork_reference,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(order_item_id) DO UPDATE SET
            status=CASE WHEN production_tasks.quantity!=excluded.quantity OR production_tasks.artwork_reference!=excluded.artwork_reference OR production_tasks.technique!=excluded.technique THEN 'pendente' ELSE production_tasks.status END,
            qc_approved=CASE WHEN production_tasks.quantity!=excluded.quantity OR production_tasks.artwork_reference!=excluded.artwork_reference OR production_tasks.technique!=excluded.technique THEN 0 ELSE production_tasks.qc_approved END,
            completed_at=CASE WHEN production_tasks.quantity!=excluded.quantity OR production_tasks.artwork_reference!=excluded.artwork_reference OR production_tasks.technique!=excluded.technique THEN '' ELSE production_tasks.completed_at END,
            art_approved=CASE WHEN production_tasks.artwork_reference!=excluded.artwork_reference THEN 0 ELSE production_tasks.art_approved END,
            quantity=excluded.quantity,technique=excluded.technique,art_required=excluded.art_required,
            artwork_reference=excluded.artwork_reference,updated_at=excluded.updated_at""",
            (item_id, quantity, technique, int(bool(art_reference)), art_reference, now, now),
        )

    def remove_for_item(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM production_tasks WHERE order_item_id=?", (item_id,))

    def start(self, item_id: int, now: str) -> None:
        self.conn.execute(
            "UPDATE production_tasks SET status='em_producao',updated_at=? WHERE order_item_id=? AND status='pendente'",
            (now, item_id),
        )

    def approve_art(self, item_id: int, now: str) -> None:
        self.conn.execute(
            "UPDATE production_tasks SET art_approved=1,updated_at=? WHERE order_item_id=?", (now, item_id)
        )

    def complete(self, item_id: int, qc_passed: bool, now: str) -> None:
        self.conn.execute(
            "UPDATE production_tasks SET status='concluida',qc_approved=?,completed_at=?,updated_at=? WHERE order_item_id=?",
            (int(qc_passed), now, now, item_id),
        )
