from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection, Row

from db import transaction
from repositories.logs import LogRepository
from repositories.products import ProductRepository
from repositories.variants import VariantRepository
from services.image_service import ImageService
from services.inventory_service import EventSink, InventoryService
from utils import cents_to_money, money_to_cents, now_iso, to_json

PROD_PRINT_ON_DEMAND = "print_on_demand"
PROD_STOCK_FISICO = "stock_fisico"
PROD_MISTO = "misto"
PRODUCTION_TYPES = {PROD_PRINT_ON_DEMAND, PROD_STOCK_FISICO, PROD_MISTO}


class ProductService:
    def __init__(
        self,
        conn: Connection,
        products: ProductRepository,
        logs: LogRepository,
        events: EventSink | None = None,
        images: ImageService | None = None,
        inventory: InventoryService | None = None,
    ) -> None:
        self.conn = conn
        self.products = products
        self.logs = logs
        self.events = events
        self.images = images
        self.variants = VariantRepository(conn)
        self.inventory = inventory or InventoryService(conn, events)

    def _changed(self) -> None:
        if self.events is not None:
            self.events.emit("products")

    def list_products(self) -> list[Row]:
        return self.products.list_all()

    def create_product(self, payload: dict[str, object]) -> int:
        data = self._validate_payload(payload)
        with transaction(self.conn):
            existing = self.products.get_by_sku(str(data["sku"]))
            if existing is not None or self.variants.get_by_sku(str(data["sku"])) is not None:
                raise ValueError("SKU já existe")
            product_id = self.products.create(data)
            variant = self.variants.ensure_default(product_id)
            if int(data["stock"]):
                self.inventory.inventory.movement(
                    int(variant["id"]), "opening", int(data["stock"]), 0, "Stock inicial", now_iso()
                )
            self.logs.create(now_iso(), "products", str(product_id), "create", "Produto criado", to_json(data))
        self._changed()
        return product_id

    def update_product(self, product_id: int, payload: dict[str, object]) -> None:
        with transaction(self.conn):
            current = self.products.get_by_id(product_id)
            if current is None:
                raise ValueError("Produto não encontrado")
            defaults = {
                **dict(current),
                "preco": str(cents_to_money(current["preco_cents"])),
                "custo": str(cents_to_money(current["custo_cents"])),
            }
            data = self._validate_payload({**defaults, **payload})
            existing = self.products.get_by_sku(str(data["sku"]))
            if existing is not None and int(existing["id"]) != product_id:
                raise ValueError("SKU já existe")
            variant_conflict = self.variants.get_by_sku(str(data["sku"]))
            base = self.variants.ensure_default(product_id)
            if variant_conflict is not None and int(variant_conflict["id"]) != int(base["id"]):
                raise ValueError("SKU já existe")
            refreshed = self.products.get_by_id(product_id)
            assert refreshed is not None
            stock_delta = int(data["stock"]) - int(refreshed["stock"])
            if stock_delta:
                self.inventory.adjust_stock(int(base["id"]), stock_delta, "Correção de stock no catálogo")
            self.products.update(product_id, data)
            self.variants.sync_default_metadata(product_id, now_iso())
            self.logs.create(now_iso(), "products", str(product_id), "update", "Produto atualizado", to_json(data))

        self._changed()

    def archive_product(self, product_id: int) -> None:
        with transaction(self.conn):
            if self.products.get_by_id(product_id) is None:
                raise ValueError("Produto não encontrado")
            self.products.archive(product_id, now_iso())
            self.logs.create(now_iso(), "products", str(product_id), "archive", "Produto arquivado", "{}")
        self._changed()

    def list_variants(self, product_id: int) -> list[Row]:
        return self.variants.list_for_product(product_id)

    def get_default_variant(self, product_id: int) -> Row | None:
        return self.variants.get_default(product_id)

    def create_variant(self, product_id: int, payload: dict[str, object]) -> int:
        with transaction(self.conn):
            product = self.products.get_by_id(product_id)
            if product is None or not int(product["ativo"]):
                raise ValueError("Produto inválido ou arquivado")
            data = self._variant_payload(payload, product_id)
            if (
                self.variants.get_by_sku(str(data["sku"])) is not None
                or self.products.get_by_sku(str(data["sku"])) is not None
            ):
                raise ValueError("SKU já existe")
            variant_id = self.variants.create(data)
            self.inventory.inventory.movement(
                variant_id, "opening", int(data["stock_on_hand"]), 0, "Stock inicial da variante", now_iso()
            )
            self.variants.sync_product_available(product_id, now_iso())
            self.logs.create(now_iso(), "product_variants", str(variant_id), "create", "Variante criada", to_json(data))
        self._changed()
        return variant_id

    def update_variant(self, variant_id: int, payload: dict[str, object]) -> None:
        with transaction(self.conn):
            current = self.variants.get(variant_id)
            if current is None:
                raise ValueError("Variante não encontrada")
            data = self._variant_payload(
                {
                    **dict(current),
                    "preco": str(cents_to_money(current["preco_cents"])),
                    "custo": str(cents_to_money(current["custo_cents"])),
                    **payload,
                },
                int(current["product_id"]),
            )
            conflict = self.variants.get_by_sku(str(data["sku"]))
            product_conflict = self.products.get_by_sku(str(data["sku"]))
            if (conflict is not None and int(conflict["id"]) != variant_id) or (
                product_conflict is not None
                and (not int(current["is_default"]) or int(product_conflict["id"]) != int(current["product_id"]))
            ):
                raise ValueError("SKU já existe")
            delta = int(data["stock_on_hand"]) - int(current["stock_on_hand"])
            if delta:
                self.inventory.adjust_stock(
                    variant_id, delta, str(payload.get("reason", "Correção de stock da variante"))
                )
            self.variants.update(variant_id, data)
            if int(current["is_default"]):
                self.products.update_base_variant_metadata(int(current["product_id"]), data)
            self.variants.sync_product_available(int(current["product_id"]), now_iso())
            self.logs.create(
                now_iso(), "product_variants", str(variant_id), "update", "Variante atualizada", to_json(data)
            )
        self._changed()

    def _variant_payload(self, payload: dict[str, object], product_id: int) -> dict[str, object]:
        sku = str(payload.get("sku", "")).strip().upper()
        if not sku:
            raise ValueError("SKU é obrigatório")
        price, cost = money_to_cents(payload.get("preco", "0")), money_to_cents(payload.get("custo", "0"))
        stock = int(payload.get("stock_on_hand", payload.get("stock", 0)))
        active = int(payload.get("ativo", 1))
        if price < 0 or cost < 0 or stock < 0 or active not in (0, 1):
            raise ValueError("Preço, custo, stock ou estado da variante inválido")
        return {
            "product_id": product_id,
            "sku": sku,
            "tamanho": str(payload.get("tamanho", "")).strip(),
            "cor": str(payload.get("cor", "")).strip(),
            "preco_cents": price,
            "custo_cents": cost,
            "stock_on_hand": stock,
            "ativo": active,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

    def list_inventory_movements(self, variant_id: int | None = None) -> list[Row]:
        return self.inventory.list_movements(variant_id)

    def adjust_stock(self, variant_id: int, quantity: int, reason: str) -> None:
        self.inventory.adjust_stock(variant_id, quantity, reason)
        self._changed()

    def set_product_technique(self, product_id: int, technique: str) -> None:
        with transaction(self.conn):
            if self.products.get_by_id(product_id) is None:
                raise ValueError("Produto não encontrado")
            self.products.set_technique(product_id, technique.strip(), now_iso())
            self.logs.create(
                now_iso(),
                "products",
                str(product_id),
                "technique",
                "Técnica de produção atualizada",
                to_json({"technique": technique.strip()}),
            )
        self._changed()

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

        ativo = int(payload.get("ativo", 1))
        if ativo not in (0, 1):
            raise ValueError("Estado do produto inválido")
        image_path = str(payload.get("image_path", "")).strip()
        if image_path and self.images is not None:
            if Path(image_path).is_absolute():
                image_path = self.images.import_image(image_path).image_path
            else:
                self.images.resolve(image_path)
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
            "image_path": image_path,
            "technique": str(payload.get("technique", "")).strip(),
            "ativo": ativo,
            "created_at": str(payload.get("created_at", now)),
            "updated_at": now,
        }
