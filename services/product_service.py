from __future__ import annotations

from sqlite3 import Connection, Row

from db import transaction
from repositories.logs import LogRepository
from repositories.products import ProductRepository
from utils import cents_to_money, money_to_cents, now_iso, to_json

PROD_PRINT_ON_DEMAND = "print_on_demand"
PROD_STOCK_FISICO = "stock_fisico"
PROD_MISTO = "misto"
PRODUCTION_TYPES = {PROD_PRINT_ON_DEMAND, PROD_STOCK_FISICO, PROD_MISTO}


class ProductService:
    def __init__(self, conn: Connection, products: ProductRepository, logs: LogRepository) -> None:
        self.conn = conn
        self.products = products
        self.logs = logs

    def list_products(self) -> list[Row]:
        return self.products.list_all()

    def create_product(self, payload: dict[str, object]) -> int:
        data = self._validate_payload(payload)
        with transaction(self.conn):
            existing = self.products.get_by_sku(str(data["sku"]))
            if existing is not None:
                raise ValueError("SKU já existe")
            product_id = self.products.create(data)
            self.logs.create(now_iso(), "products", str(product_id), "create", "Produto criado", to_json(data))
        return product_id

    def update_product(self, product_id: int, payload: dict[str, object]) -> None:
        current = self.products.get_by_id(product_id)
        if current is None:
            raise ValueError("Produto não encontrado")
        data = self._validate_payload(payload)
        with transaction(self.conn):
            existing = self.products.get_by_sku(str(data["sku"]))
            if existing is not None and int(existing["id"]) != product_id:
                raise ValueError("SKU já existe")
            self.products.update(product_id, data)
            self.logs.create(now_iso(), "products", str(product_id), "update", "Produto atualizado", to_json(data))

    def get_product(self, product_id: int) -> Row | None:
        return self.products.get_by_id(product_id)

    def _validate_payload(self, payload: dict[str, object]) -> dict[str, object]:
        nome = str(payload.get("nome", "")).strip()
        sku = str(payload.get("sku", "")).strip().upper()
        if not nome:
            raise ValueError("Nome é obrigatório")
        if not sku:
            raise ValueError("SKU é obrigatório")

        preco_cents = money_to_cents(payload.get("preco", "0"))
        custo_cents = money_to_cents(payload.get("custo", "0"))
        stock = int(payload.get("stock", 0))
        stock_minimo = int(payload.get("stock_minimo", 0))
        if preco_cents < 0:
            raise ValueError("Preço deve ser >= 0")
        if custo_cents < 0:
            raise ValueError("Custo deve ser >= 0")
        if stock < 0:
            raise ValueError("Stock deve ser >= 0")
        if stock_minimo < 0:
            raise ValueError("Stock mínimo deve ser >= 0")
        tipo_producao = str(payload.get("tipo_producao", PROD_PRINT_ON_DEMAND)).strip().lower()
        if tipo_producao not in PRODUCTION_TYPES:
            raise ValueError("Tipo de produção inválido")

        now = now_iso()
        return {
            "sku": sku,
            "nome": nome,
            "descricao": str(payload.get("descricao", "")).strip(),
            "preco_cents": preco_cents,
            "custo_cents": custo_cents,
            "preco": float(cents_to_money(preco_cents)),
            "custo": float(cents_to_money(custo_cents)),
            "stock": stock,
            "stock_minimo": stock_minimo,
            "tipo_producao": tipo_producao,
            "image_path": str(payload.get("image_path", "")).strip(),
            "ativo": int(payload.get("ativo", 1)),
            "created_at": str(payload.get("created_at", now)),
            "updated_at": now,
        }
