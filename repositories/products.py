from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class ProductRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def list_all(self) -> list[Row]:
        return self.conn.execute(
            """
            SELECT id, sku, nome, descricao,
                   preco_cents,
                   custo_cents,
                   preco_cents / 100.0 AS preco,
                   custo_cents / 100.0 AS custo,
                   stock, stock_minimo, tipo_producao, image_path, ativo, created_at, updated_at, technique,
                   (SELECT COALESCE(SUM(stock_on_hand),0) FROM product_variants v WHERE v.product_id=products.id) AS stock_on_hand,
                   (SELECT COALESCE(SUM(stock_reserved),0) FROM product_variants v WHERE v.product_id=products.id) AS stock_reserved,
                   stock AS stock_available
            FROM products
            ORDER BY id DESC
            """
        ).fetchall()

    def get_by_id(self, product_id: int) -> Row | None:
        return self.conn.execute(
            """
            SELECT *, preco_cents / 100.0 AS preco, custo_cents / 100.0 AS custo,
                   stock AS stock_available,
                   (SELECT COALESCE(SUM(stock_on_hand),0) FROM product_variants v WHERE v.product_id=products.id) AS stock_on_hand,
                   (SELECT COALESCE(SUM(stock_reserved),0) FROM product_variants v WHERE v.product_id=products.id) AS stock_reserved
            FROM products
            WHERE id = ?
            """,
            (product_id,),
        ).fetchone()

    def get_by_sku(self, sku: str) -> Row | None:
        return self.conn.execute(
            "SELECT *, preco_cents / 100.0 AS preco, custo_cents / 100.0 AS custo FROM products WHERE sku = ?",
            (sku,),
        ).fetchone()

    def create(self, data: dict[str, object]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO products (sku, nome, descricao, preco_cents, custo_cents, stock, stock_minimo, tipo_producao, image_path, ativo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["sku"],
                data["nome"],
                data["descricao"],
                data["preco_cents"],
                data["custo_cents"],
                data["stock"],
                data["stock_minimo"],
                data["tipo_producao"],
                data["image_path"],
                data["ativo"],
                data["created_at"],
                data["updated_at"],
            ),
        )
        product_id = require_lastrowid(cursor, "products")
        self.conn.execute("UPDATE products SET technique=? WHERE id=?", (str(data.get("technique", "")), product_id))
        return product_id

    def update(self, product_id: int, data: dict[str, object]) -> None:
        self.conn.execute(
            """
            UPDATE products
            SET sku = ?, nome = ?, descricao = ?, preco_cents = ?, custo_cents = ?, stock = ?, stock_minimo = ?,
                tipo_producao = ?, image_path = ?, ativo = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["sku"],
                data["nome"],
                data["descricao"],
                data["preco_cents"],
                data["custo_cents"],
                data["stock"],
                data["stock_minimo"],
                data["tipo_producao"],
                data["image_path"],
                data["ativo"],
                data["updated_at"],
                product_id,
            ),
        )
        self.conn.execute("UPDATE products SET technique=? WHERE id=?", (str(data.get("technique", "")), product_id))

    def update_base_variant_metadata(self, product_id: int, data: dict[str, object]) -> None:
        self.conn.execute(
            "UPDATE products SET sku=?,preco_cents=?,custo_cents=?,updated_at=? WHERE id=?",
            (data["sku"], data["preco_cents"], data["custo_cents"], data["updated_at"], product_id),
        )

    def archive(self, product_id: int, now: str) -> None:
        self.conn.execute("UPDATE products SET ativo=0,updated_at=? WHERE id=?", (now, product_id))
        self.conn.execute("UPDATE product_variants SET ativo=0,updated_at=? WHERE product_id=?", (now, product_id))

    def set_technique(self, product_id: int, technique: str, now: str) -> None:
        self.conn.execute("UPDATE products SET technique=?,updated_at=? WHERE id=?", (technique, now, product_id))

    def decrement_stock(self, product_id: int, quantity: int, updated_at: str) -> None:
        self.conn.execute(
            "UPDATE products SET stock = stock - ?, updated_at = ? WHERE id = ?",
            (quantity, updated_at, product_id),
        )

    def increment_stock(self, product_id: int, quantity: int, updated_at: str) -> None:
        self.conn.execute(
            "UPDATE products SET stock = stock + ?, updated_at = ? WHERE id = ?",
            (quantity, updated_at, product_id),
        )
