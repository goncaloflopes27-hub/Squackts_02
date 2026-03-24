from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class ProductRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def list_all(self) -> list[Row]:
        return self.conn.execute(
            """
            SELECT id, sku, nome, cor, tamanhos_json, descricao,
                   preco_cents,
                   custo_cents,
                   preco_cents / 100.0 AS preco,
                   custo_cents / 100.0 AS custo,
                   stock, stock_minimo, tipo_producao, image_path, ativo, created_at, updated_at
            FROM products
            ORDER BY id DESC
            """
        ).fetchall()

    def get_by_id(self, product_id: int) -> Row | None:
        return self.conn.execute(
            """
            SELECT *, preco_cents / 100.0 AS preco, custo_cents / 100.0 AS custo
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
            INSERT INTO products (sku, nome, cor, tamanhos_json, descricao, preco_cents, custo_cents, stock, stock_minimo, tipo_producao, image_path, ativo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["sku"],
                data["nome"],
                data["cor"],
                data["tamanhos_json"],
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
        return require_lastrowid(cursor, "products")

    def update(self, product_id: int, data: dict[str, object]) -> None:
        self.conn.execute(
            """
            UPDATE products
            SET sku = ?, nome = ?, cor = ?, tamanhos_json = ?, descricao = ?, preco_cents = ?, custo_cents = ?, stock = ?, stock_minimo = ?,
                tipo_producao = ?, image_path = ?, ativo = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["sku"],
                data["nome"],
                data["cor"],
                data["tamanhos_json"],
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

    def sku_exists(self, sku: str, exclude_product_id: int | None = None) -> bool:
        if exclude_product_id is None:
            row = self.conn.execute("SELECT 1 FROM products WHERE sku = ? LIMIT 1", (sku,)).fetchone()
            return row is not None
        row = self.conn.execute("SELECT 1 FROM products WHERE sku = ? AND id != ? LIMIT 1", (sku, exclude_product_id)).fetchone()
        return row is not None

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
