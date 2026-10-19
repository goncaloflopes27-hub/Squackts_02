from __future__ import annotations

from sqlite3 import Connection, Row

from repositories._helpers import require_lastrowid


class VariantRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def list_for_product(self, product_id: int) -> list[Row]:
        return self.conn.execute(
            "SELECT *, stock_on_hand-stock_reserved AS stock_available, preco_cents/100.0 AS preco, custo_cents/100.0 AS custo FROM product_variants WHERE product_id=? ORDER BY is_default DESC,id",
            (product_id,),
        ).fetchall()

    def get(self, variant_id: int) -> Row | None:
        return self.conn.execute(
            "SELECT *, stock_on_hand-stock_reserved AS stock_available, preco_cents/100.0 AS preco, custo_cents/100.0 AS custo FROM product_variants WHERE id=?", (variant_id,)
        ).fetchone()

    def get_by_sku(self, sku: str) -> Row | None:
        return self.conn.execute("SELECT *, stock_on_hand-stock_reserved AS stock_available, preco_cents/100.0 AS preco, custo_cents/100.0 AS custo FROM product_variants WHERE sku=?", (sku,)).fetchone()

    def sync_default_metadata(self, product_id: int, now: str) -> None:
        self.conn.execute(
            """UPDATE product_variants SET
            sku=(SELECT sku FROM products WHERE id=?),
            preco_cents=(SELECT preco_cents FROM products WHERE id=?),
            custo_cents=(SELECT custo_cents FROM products WHERE id=?),
            ativo=(SELECT ativo FROM products WHERE id=?),updated_at=?
            WHERE product_id=? AND is_default=1""",
            (product_id, product_id, product_id, product_id, now, product_id),
        )

    def get_default(self, product_id: int) -> Row | None:
        return self.conn.execute(
            "SELECT *, stock_on_hand-stock_reserved AS stock_available, preco_cents/100.0 AS preco, custo_cents/100.0 AS custo FROM product_variants WHERE product_id=? AND is_default=1",
            (product_id,),
        ).fetchone()

    def ensure_default(self, product_id: int) -> Row:
        self.conn.execute(
            """INSERT INTO product_variants
            (product_id,sku,preco_cents,custo_cents,stock_on_hand,ativo,is_default,created_at,updated_at)
            SELECT id,sku,preco_cents,custo_cents,stock,ativo,1,created_at,updated_at FROM products
            WHERE id=? AND NOT EXISTS(SELECT 1 FROM product_variants WHERE product_id=? AND is_default=1)
        """,
            (product_id, product_id),
        )
        variant = self.get_default(product_id)
        if variant is None:
            raise ValueError("Produto não encontrado")
        return variant

    def create(self, data: dict[str, object]) -> int:
        cursor = self.conn.execute(
            """INSERT INTO product_variants
            (product_id,sku,tamanho,cor,preco_cents,custo_cents,stock_on_hand,ativo,is_default,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
            (
                data["product_id"],
                data["sku"],
                data["tamanho"],
                data["cor"],
                data["preco_cents"],
                data["custo_cents"],
                data["stock_on_hand"],
                data["ativo"],
                data["created_at"],
                data["updated_at"],
            ),
        )
        return require_lastrowid(cursor, "product_variants")

    def update(self, variant_id: int, data: dict[str, object]) -> None:
        self.conn.execute(
            """UPDATE product_variants SET sku=?,tamanho=?,cor=?,preco_cents=?,custo_cents=?,ativo=?,updated_at=? WHERE id=?""",
            (
                data["sku"],
                data["tamanho"],
                data["cor"],
                data["preco_cents"],
                data["custo_cents"],
                data["ativo"],
                data["updated_at"],
                variant_id,
            ),
        )

    def set_balances(self, variant_id: int, physical_delta: int, reserved_delta: int, now: str) -> bool:
        cursor = self.conn.execute(
            """UPDATE product_variants
            SET stock_on_hand=stock_on_hand+?,stock_reserved=stock_reserved+?,updated_at=?
            WHERE id=? AND stock_on_hand+?>=0 AND stock_reserved+?>=0
            AND stock_on_hand+?>=stock_reserved+?""",
            (
                physical_delta,
                reserved_delta,
                now,
                variant_id,
                physical_delta,
                reserved_delta,
                physical_delta,
                reserved_delta,
            ),
        )
        return cursor.rowcount == 1

    def sync_product_available(self, product_id: int, now: str) -> None:
        self.conn.execute(
            """UPDATE products SET stock=(SELECT COALESCE(SUM(stock_on_hand-stock_reserved),0)
            FROM product_variants WHERE product_id=products.id),updated_at=? WHERE id=?""",
            (now, product_id),
        )
