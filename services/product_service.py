from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from sqlite3 import Connection, Row

from PIL import Image, UnidentifiedImageError

from config import PATHS
from db import transaction
from repositories.logs import LogRepository
from repositories.products import ProductRepository
from utils import cents_to_money, money_to_cents, now_iso, to_json

logger = logging.getLogger(__name__)

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
            data["sku"] = self._generate_unique_sku(str(data["nome"]), str(data["cor"]))
            product_id = self.products.create(data)
            self.logs.create(now_iso(), "products", str(product_id), "create", "Produto criado", to_json(data))
        return product_id

    def update_product(self, product_id: int, payload: dict[str, object]) -> None:
        current = self.products.get_by_id(product_id)
        if current is None:
            raise ValueError("Produto não encontrado")
        data = self._validate_payload(payload)
        with transaction(self.conn):
            data["sku"] = self._generate_unique_sku(str(data["nome"]), str(data["cor"]), exclude_product_id=product_id)
            self.products.update(product_id, data)
            self.logs.create(now_iso(), "products", str(product_id), "update", "Produto atualizado", to_json(data))

    def get_product(self, product_id: int) -> Row | None:
        return self.products.get_by_id(product_id)

    def prepare_image_asset(self, source_path: str, sku_hint: str) -> str:
        raw = Path(source_path).expanduser().resolve()
        if not raw.exists() or not raw.is_file():
            raise ValueError("Ficheiro de imagem não encontrado")

        products_dir = PATHS.images_dir / "products"
        products_dir.mkdir(parents=True, exist_ok=True)
        token = self._slug_token(sku_hint or raw.stem, 6)
        target = products_dir / f"{token}.png"
        target = self._next_available_image_target(target)

        try:
            with Image.open(raw) as image:
                image.load()
                normalized = image.convert("RGBA")
                normalized.thumbnail((960, 960), Image.Resampling.LANCZOS)
                normalized.save(target, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError) as exc:
            logger.warning("Invalid image selected: %s", raw)
            raise ValueError("Imagem inválida ou corrompida") from exc

        return str(target)


    def _next_available_image_target(self, preferred: Path) -> Path:
        if not preferred.exists():
            return preferred
        stem = preferred.stem
        suffix = preferred.suffix
        index = 2
        while True:
            candidate = preferred.with_name(f"{stem}-{index:02d}{suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    def _validate_payload(self, payload: dict[str, object]) -> dict[str, object]:
        nome = str(payload.get("nome", "")).strip()
        cor = str(payload.get("cor", "")).strip()
        if not nome:
            raise ValueError("Nome é obrigatório")
        if not cor:
            raise ValueError("Cor é obrigatória")

        tamanhos = self._normalize_sizes(payload.get("tamanhos", []))

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
            "sku": "",
            "nome": nome,
            "cor": cor,
            "tamanhos_json": json.dumps(tamanhos, ensure_ascii=False, separators=(",", ":")),
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

    def _normalize_sizes(self, raw: object) -> list[str]:
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        ordered: list[str] = []
        for value in raw:
            size = str(value).strip().upper()
            if not size or size in seen:
                continue
            seen.add(size)
            ordered.append(size)
        return ordered

    def _generate_unique_sku(self, nome: str, cor: str, *, exclude_product_id: int | None = None) -> str:
        base = self._generate_base_sku(nome, cor)
        if not self.products.sku_exists(base, exclude_product_id):
            return base
        index = 2
        while True:
            candidate = f"{base}-{index:02d}"
            if not self.products.sku_exists(candidate, exclude_product_id):
                return candidate
            index += 1

    def _generate_base_sku(self, nome: str, cor: str) -> str:
        nome_token = self._slug_token(nome, 4)
        cor_token = self._slug_token(cor, 3)
        return f"{nome_token}-{cor_token}"

    def _slug_token(self, raw: str, min_len: int) -> str:
        normalized = unicodedata.normalize("NFKD", raw)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        collapsed = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").upper()
        if not collapsed:
            collapsed = "X" * min_len
        if len(collapsed) < min_len:
            collapsed = collapsed.ljust(min_len, "X")
        return collapsed
