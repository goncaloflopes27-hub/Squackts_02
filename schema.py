from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from config import SCHEMA_USER_VERSION

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    cor TEXT NOT NULL DEFAULT '',
    tamanhos_json TEXT NOT NULL DEFAULT '[]',
    descricao TEXT NOT NULL DEFAULT '',
    preco_cents INTEGER NOT NULL CHECK (preco_cents >= 0),
    custo_cents INTEGER NOT NULL CHECK (custo_cents >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    tipo_producao TEXT NOT NULL CHECK (tipo_producao IN ('print_on_demand', 'stock_fisico', 'misto')),
    image_path TEXT NOT NULL DEFAULT '',
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    telefone TEXT NOT NULL DEFAULT '',
    nif TEXT NOT NULL DEFAULT '',
    morada TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    client_id INTEGER NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('rascunho', 'confirmada', 'paga', 'em_producao', 'pronta_envio', 'expedida', 'concluida', 'cancelada')),
    pago INTEGER NOT NULL DEFAULT 0 CHECK (pago IN (0, 1)),
    tracking TEXT NOT NULL DEFAULT '',
    metodo_pagamento TEXT NOT NULL DEFAULT '',
    subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    portes_cents INTEGER NOT NULL CHECK (portes_cents >= 0),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    data_prevista TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    sku_snapshot TEXT NOT NULL,
    nome_snapshot TEXT NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unit_cents INTEGER NOT NULL CHECK (preco_unit_cents >= 0),
    custo_unit_cents INTEGER NOT NULL CHECK (custo_unit_cents >= 0),
    tipo_producao_snapshot TEXT NOT NULL,
    stock_deducted INTEGER NOT NULL DEFAULT 0 CHECK (stock_deducted IN (0, 1)),
    stock_returned INTEGER NOT NULL DEFAULT 0 CHECK (stock_returned IN (0, 1)),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    entidade TEXT NOT NULL,
    entidade_id TEXT NOT NULL DEFAULT '',
    acao TEXT NOT NULL,
    detalhe TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id);
CREATE INDEX IF NOT EXISTS idx_orders_estado ON orders(estado);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_email_unique
ON clients(lower(email))
WHERE email <> '';
"""


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.commit()
    _migrate_clients_table(conn)
    _migrate_products_table(conn)
    _migrate_orders_table(conn)
    _migrate_order_items_table(conn)
    conn.executescript(SCHEMA_SQL)
    _normalize_legacy_values(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    _validate_foreign_keys(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION}")
    conn.commit()




def _normalize_legacy_values(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE products SET tipo_producao = 'print_on_demand' WHERE LOWER(tipo_producao) IN ('dtg', 'dtf', 'sublimação', 'bordado', 'uv', 'giclée')")
    conn.execute("UPDATE products SET tipo_producao = 'print_on_demand' WHERE tipo_producao NOT IN ('print_on_demand', 'stock_fisico', 'misto')")
    conn.execute("UPDATE orders SET estado = 'confirmada' WHERE estado = 'pendente'")
    conn.execute("UPDATE orders SET estado = 'em_producao' WHERE estado = 'producao'")
    conn.execute("UPDATE orders SET estado = 'pronta_envio' WHERE estado = 'qc'")
    conn.execute("UPDATE orders SET estado = 'expedida' WHERE estado = 'enviado'")
    conn.execute(
        "UPDATE orders SET estado = 'rascunho' WHERE estado NOT IN ('rascunho', 'confirmada', 'paga', 'em_producao', 'pronta_envio', 'expedida', 'concluida', 'cancelada')"
    )

def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    if row is None or row[0] is None:
        return ""
    return str(row[0]).lower()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]).lower() for row in rows}


def _migrate_products_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "products")
    if not sql:
        return
    columns = _table_columns(conn, "products")
    if {"preco_cents", "custo_cents", "cor", "tamanhos_json"}.issubset(columns) and "print_on_demand" in sql:
        return

    has_preco_cents = "preco_cents" in columns
    has_custo_cents = "custo_cents" in columns
    has_cor = "cor" in columns
    has_tamanhos_json = "tamanhos_json" in columns
    preco_expr = "CAST(preco_cents AS INTEGER)" if has_preco_cents else "CAST(ROUND(COALESCE(preco, 0) * 100.0) AS INTEGER)"
    custo_expr = "CAST(custo_cents AS INTEGER)" if has_custo_cents else "CAST(ROUND(COALESCE(custo, 0) * 100.0) AS INTEGER)"
    # Migração legacy (nome sem cor separada): não inferimos automaticamente "cor" a partir de "nome"
    # para evitar separações erradas/destrutivas. Nesses casos, "cor" fica explicitamente vazia.
    cor_expr = "TRIM(COALESCE(cor, ''))" if has_cor else "''"
    tamanhos_expr = "COALESCE(tamanhos_json, '[]')" if has_tamanhos_json else "'[]'"

    with _foreign_keys_temporarily_off(conn):
        conn.execute("DROP TABLE IF EXISTS products__new")
        conn.execute(
            """
            CREATE TABLE products__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                cor TEXT NOT NULL DEFAULT '',
                tamanhos_json TEXT NOT NULL DEFAULT '[]',
                descricao TEXT NOT NULL DEFAULT '',
                preco_cents INTEGER NOT NULL CHECK (preco_cents >= 0),
                custo_cents INTEGER NOT NULL CHECK (custo_cents >= 0),
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
                tipo_producao TEXT NOT NULL CHECK (tipo_producao IN ('print_on_demand', 'stock_fisico', 'misto')),
                image_path TEXT NOT NULL DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO products__new
                (id, sku, nome, cor, tamanhos_json, descricao, preco_cents, custo_cents, stock, stock_minimo, tipo_producao, image_path, ativo, created_at, updated_at)
            SELECT
                id,
                sku,
                nome,
                {cor_expr},
                {tamanhos_expr},
                descricao,
                {preco_expr},
                {custo_expr},
                stock,
                stock_minimo,
                CASE
                    WHEN LOWER(tipo_producao) IN ('stock_fisico', 'misto', 'print_on_demand') THEN LOWER(tipo_producao)
                    ELSE 'print_on_demand'
                END,
                image_path,
                ativo,
                created_at,
                updated_at
            FROM products
            """
        )
        conn.execute("DROP TABLE products")
        conn.execute("ALTER TABLE products__new RENAME TO products")


def _migrate_clients_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "clients")
    if not sql:
        return
    normalized_sql = " ".join(sql.split())
    if "email text not null default ''" in normalized_sql:
        return

    with _foreign_keys_temporarily_off(conn):
        conn.execute("DROP TABLE IF EXISTS clients__new")
        conn.execute(
            """
            CREATE TABLE clients__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                telefone TEXT NOT NULL DEFAULT '',
                nif TEXT NOT NULL DEFAULT '',
                morada TEXT NOT NULL DEFAULT '',
                notas TEXT NOT NULL DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO clients__new
                (id, nome, email, telefone, nif, morada, notas, ativo, created_at, updated_at)
            SELECT
                id,
                nome,
                TRIM(COALESCE(email, '')),
                telefone,
                nif,
                morada,
                notas,
                ativo,
                created_at,
                updated_at
            FROM clients
            """
        )
        conn.execute("DROP TABLE clients")
        conn.execute("ALTER TABLE clients__new RENAME TO clients")


def _migrate_orders_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "orders")
    if not sql:
        return
    if "subtotal_cents" in sql and "portes_cents" in sql and "total_cents" in sql and "pronta_envio" in sql:
        return

    has_subtotal_cents = "subtotal_cents" in sql
    has_portes_cents = "portes_cents" in sql
    has_total_cents = "total_cents" in sql
    subtotal_expr = "CAST(subtotal_cents AS INTEGER)" if has_subtotal_cents else "CAST(ROUND(COALESCE(subtotal, 0) * 100.0) AS INTEGER)"
    portes_expr = "CAST(portes_cents AS INTEGER)" if has_portes_cents else "CAST(ROUND(COALESCE(portes, 0) * 100.0) AS INTEGER)"
    total_expr = "CAST(total_cents AS INTEGER)" if has_total_cents else "CAST(ROUND(COALESCE(total, 0) * 100.0) AS INTEGER)"

    with _foreign_keys_temporarily_off(conn):
        conn.execute("DROP TABLE IF EXISTS orders__new")
        conn.execute(
            """
            CREATE TABLE orders__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero TEXT NOT NULL UNIQUE,
                client_id INTEGER NOT NULL,
                estado TEXT NOT NULL CHECK (estado IN ('rascunho', 'confirmada', 'paga', 'em_producao', 'pronta_envio', 'expedida', 'concluida', 'cancelada')),
                pago INTEGER NOT NULL DEFAULT 0 CHECK (pago IN (0, 1)),
                tracking TEXT NOT NULL DEFAULT '',
                metodo_pagamento TEXT NOT NULL DEFAULT '',
                subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
                portes_cents INTEGER NOT NULL CHECK (portes_cents >= 0),
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                data_prevista TEXT NOT NULL DEFAULT '',
                notas TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO orders__new
                (id, numero, client_id, estado, pago, tracking, metodo_pagamento, subtotal_cents, portes_cents, total_cents, data_prevista, notas, created_at, updated_at)
            SELECT
                id,
                numero,
                client_id,
                CASE
                    WHEN estado = 'pendente' THEN 'confirmada'
                    WHEN estado = 'producao' THEN 'em_producao'
                    WHEN estado = 'qc' THEN 'pronta_envio'
                    WHEN estado = 'enviado' THEN 'expedida'
                    WHEN estado IN ('rascunho', 'confirmada', 'paga', 'em_producao', 'pronta_envio', 'expedida', 'concluida', 'cancelada') THEN estado
                    ELSE 'rascunho'
                END,
                pago,
                tracking,
                metodo_pagamento,
                {subtotal_expr},
                {portes_expr},
                {total_expr},
                data_prevista,
                notas,
                created_at,
                updated_at
            FROM orders
            """
        )
        conn.execute("DROP TABLE orders")
        conn.execute("ALTER TABLE orders__new RENAME TO orders")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_estado ON orders(estado)")


def _migrate_order_items_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "order_items")
    if not sql:
        return
    if "preco_unit_cents" in sql and "custo_unit_cents" in sql:
        return

    has_preco_unit_cents = "preco_unit_cents" in sql
    has_custo_unit_cents = "custo_unit_cents" in sql
    preco_expr = "CAST(preco_unit_cents AS INTEGER)" if has_preco_unit_cents else "CAST(ROUND(COALESCE(preco_unit, 0) * 100.0) AS INTEGER)"
    custo_expr = "CAST(custo_unit_cents AS INTEGER)" if has_custo_unit_cents else "CAST(ROUND(COALESCE(custo_unit, 0) * 100.0) AS INTEGER)"

    with _foreign_keys_temporarily_off(conn):
        conn.execute("DROP TABLE IF EXISTS order_items__new")
        conn.execute(
            """
            CREATE TABLE order_items__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sku_snapshot TEXT NOT NULL,
                nome_snapshot TEXT NOT NULL,
                quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                preco_unit_cents INTEGER NOT NULL CHECK (preco_unit_cents >= 0),
                custo_unit_cents INTEGER NOT NULL CHECK (custo_unit_cents >= 0),
                tipo_producao_snapshot TEXT NOT NULL,
                stock_deducted INTEGER NOT NULL DEFAULT 0 CHECK (stock_deducted IN (0, 1)),
                stock_returned INTEGER NOT NULL DEFAULT 0 CHECK (stock_returned IN (0, 1)),
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO order_items__new
                (id, order_id, product_id, sku_snapshot, nome_snapshot, quantidade, preco_unit_cents, custo_unit_cents, tipo_producao_snapshot, stock_deducted, stock_returned)
            SELECT
                id,
                order_id,
                product_id,
                sku_snapshot,
                nome_snapshot,
                quantidade,
                {preco_expr},
                {custo_expr},
                tipo_producao_snapshot,
                stock_deducted,
                stock_returned
            FROM order_items
            """
        )
        conn.execute("DROP TABLE order_items")
        conn.execute("ALTER TABLE order_items__new RENAME TO order_items")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)")


@contextmanager
def _foreign_keys_temporarily_off(conn: sqlite3.Connection) -> Iterator[None]:
    conn.commit()
    original_fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("SAVEPOINT schema_rebuild")
    try:
        yield
        conn.execute("RELEASE SAVEPOINT schema_rebuild")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT schema_rebuild")
        conn.execute("RELEASE SAVEPOINT schema_rebuild")
        raise
    finally:
        conn.execute(f"PRAGMA foreign_keys = {original_fk}")


def _validate_foreign_keys(conn: sqlite3.Connection) -> None:
    fk_enabled = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    if fk_enabled != 1:
        raise RuntimeError("PRAGMA foreign_keys está desligado após migração do schema")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Integridade relacional inválida após migração: {violations[:5]}")
