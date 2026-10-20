from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from config import SCHEMA_USER_VERSION
from db import backup_database
from utils import now_iso, to_json

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    preco_cents INTEGER NOT NULL CHECK (preco_cents >= 0),
    custo_cents INTEGER NOT NULL CHECK (custo_cents >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    tipo_producao TEXT NOT NULL CHECK (tipo_producao IN ('print_on_demand', 'stock_fisico', 'misto')),
    image_path TEXT NOT NULL DEFAULT '',
    technique TEXT NOT NULL DEFAULT '',
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
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
"""


def _migration_1(conn: sqlite3.Connection) -> None:
    # Preserve source technique before fulfillment normalization. Versions which
    # already discarded it are deliberately left blank rather than guessed.
    if _table_sql(conn, "products"):
        columns = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
        if "technique" not in columns:
            conn.execute("ALTER TABLE products ADD COLUMN technique TEXT NOT NULL DEFAULT ''")
        conn.execute("""UPDATE products SET technique = tipo_producao
            WHERE technique = '' AND LOWER(tipo_producao) NOT IN
            ('print_on_demand', 'stock_fisico', 'misto')""")
    # Table rebuilds retain identifiers and the legacy REAL -> cents conversion.
    _migrate_products_table(conn)
    _migrate_orders_table(conn)
    _migrate_order_items_table(conn)
    for statement in SCHEMA_SQL.split(";"):
        if statement.strip():
            conn.execute(statement)


def _migration_2(conn: sqlite3.Connection) -> None:
    _migration_1(conn)
    conn.execute(
        "UPDATE products SET tipo_producao = 'print_on_demand' WHERE tipo_producao NOT IN ('print_on_demand', 'stock_fisico', 'misto')"
    )
    for previous, current in (
        ("pendente", "confirmada"),
        ("producao", "em_producao"),
        ("qc", "pronta_envio"),
        ("enviado", "expedida"),
    ):
        conn.execute("UPDATE orders SET estado = ? WHERE estado = ?", (current, previous))


def _migration_3(conn: sqlite3.Connection) -> None:
    # Early releases had REAL-valued tables even when user_version was set.
    _migration_1(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_estado ON orders(estado)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")


def _migration_4(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    if "payment_recorded_at" not in columns:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_recorded_at TEXT NOT NULL DEFAULT ''")
    # Preserve the historical payment flag; do not invent payment or tracking.
    conn.execute("""CREATE TABLE IF NOT EXISTS reconciliation_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        detail TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT NOT NULL DEFAULT '',
        UNIQUE(order_id, code),
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    )""")
    inconsistent = conn.execute("""SELECT id, estado, pago, tracking FROM orders
        WHERE (estado = 'paga' AND pago = 0)
           OR (estado IN ('expedida', 'concluida') AND (pago = 0 OR TRIM(tracking) = ''))""").fetchall()
    for row in inconsistent:
        detail = "Registo histórico requer reconciliação do pagamento ou tracking."
        conn.execute(
            "INSERT OR IGNORE INTO reconciliation_issues(order_id, code, detail, created_at) VALUES (?, ?, ?, ?)",
            (row[0], "historical_payment_tracking", detail, now_iso()),
        )
        conn.execute(
            "INSERT INTO logs(timestamp, entidade, entidade_id, acao, detalhe, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                now_iso(),
                "order",
                str(row[0]),
                "migration_reconciliation_required",
                detail,
                to_json({"estado": row[1], "pago": row[2], "tracking": row[3]}),
            ),
        )
    conn.execute("UPDATE orders SET estado = 'confirmada' WHERE estado = 'paga'")


def _migration_5(conn: sqlite3.Connection) -> None:
    from pod_schema import apply_pod_schema

    apply_pod_schema(conn)


def _migration_6(conn: sqlite3.Connection) -> None:
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_orders_state_created ON orders(estado, created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_orders_client_created ON orders(client_id, created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_orders_updated ON orders(updated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_orders_state_updated ON orders(estado, updated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_logs_entity ON logs(entidade, entidade_id, id DESC)",
    ):
        conn.execute(statement)


def _migration_7(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    if "refund_status" not in columns:
        conn.execute("ALTER TABLE orders ADD COLUMN refund_status TEXT NOT NULL DEFAULT 'none' CHECK (refund_status IN ('none', 'pending', 'refunded'))")
    if "refund_recorded_at" not in columns:
        conn.execute("ALTER TABLE orders ADD COLUMN refund_recorded_at TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE orders SET refund_status = 'pending' WHERE estado = 'cancelada' AND pago = 1 AND total_cents > 0 AND refund_status = 'none'")


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migration_1,
    2: _migration_2,
    3: _migration_3,
    4: _migration_4,
    5: _migration_5,
    6: _migration_6,
    7: _migration_7,
}


def apply_schema(conn: sqlite3.Connection) -> None:
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_USER_VERSION:
        raise RuntimeError(f"Base de dados versão {version} mais recente que a aplicação ({SCHEMA_USER_VERSION}).")
    if version == SCHEMA_USER_VERSION:
        conn.execute("PRAGMA foreign_keys = ON")
        _validate_foreign_keys(conn)
        return
    conn.commit()
    existing = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1").fetchone()
    database_path = conn.execute("PRAGMA database_list").fetchone()[2]
    if existing and database_path:
        backup_database(conn, Path(database_path).parent / "migration_backups")
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for target in range(version + 1, SCHEMA_USER_VERSION + 1):
            MIGRATIONS[target](conn)
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError(f"Integridade relacional inválida na migração {target}.")
            conn.execute(f"PRAGMA user_version = {target}")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Integridade da base de dados inválida após migração.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    _validate_foreign_keys(conn)


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    if row is None or row[0] is None:
        return ""
    return str(row[0]).lower()


def _migrate_products_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "products")
    if not sql:
        return
    if "preco_cents" in sql and "custo_cents" in sql and "print_on_demand" in sql:
        return

    has_preco_cents = "preco_cents" in sql
    has_custo_cents = "custo_cents" in sql
    preco_expr = (
        "CAST(preco_cents AS INTEGER)" if has_preco_cents else "CAST(ROUND(COALESCE(preco, 0) * 100.0) AS INTEGER)"
    )
    custo_expr = (
        "CAST(custo_cents AS INTEGER)" if has_custo_cents else "CAST(ROUND(COALESCE(custo, 0) * 100.0) AS INTEGER)"
    )

    with _foreign_keys_temporarily_off(conn):
        conn.execute("DROP TABLE IF EXISTS products__new")
        conn.execute(
            """
            CREATE TABLE products__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                descricao TEXT NOT NULL DEFAULT '',
                preco_cents INTEGER NOT NULL CHECK (preco_cents >= 0),
                custo_cents INTEGER NOT NULL CHECK (custo_cents >= 0),
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
                tipo_producao TEXT NOT NULL CHECK (tipo_producao IN ('print_on_demand', 'stock_fisico', 'misto')),
                image_path TEXT NOT NULL DEFAULT '',
                technique TEXT NOT NULL DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO products__new
                (id, sku, nome, descricao, preco_cents, custo_cents, stock, stock_minimo, tipo_producao, image_path, technique, ativo, created_at, updated_at)
            SELECT
                id,
                sku,
                nome,
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
                technique,
                ativo,
                created_at,
                updated_at
            FROM products
            """
        )
        conn.execute("DROP TABLE products")
        conn.execute("ALTER TABLE products__new RENAME TO products")


def _migrate_orders_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "orders")
    if not sql:
        return
    if "subtotal_cents" in sql and "portes_cents" in sql and "total_cents" in sql and "pronta_envio" in sql:
        return

    has_subtotal_cents = "subtotal_cents" in sql
    has_portes_cents = "portes_cents" in sql
    has_total_cents = "total_cents" in sql
    subtotal_expr = (
        "CAST(subtotal_cents AS INTEGER)"
        if has_subtotal_cents
        else "CAST(ROUND(COALESCE(subtotal, 0) * 100.0) AS INTEGER)"
    )
    portes_expr = (
        "CAST(portes_cents AS INTEGER)" if has_portes_cents else "CAST(ROUND(COALESCE(portes, 0) * 100.0) AS INTEGER)"
    )
    total_expr = (
        "CAST(total_cents AS INTEGER)" if has_total_cents else "CAST(ROUND(COALESCE(total, 0) * 100.0) AS INTEGER)"
    )

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
    preco_expr = (
        "CAST(preco_unit_cents AS INTEGER)"
        if has_preco_unit_cents
        else "CAST(ROUND(COALESCE(preco_unit, 0) * 100.0) AS INTEGER)"
    )
    custo_expr = (
        "CAST(custo_unit_cents AS INTEGER)"
        if has_custo_unit_cents
        else "CAST(ROUND(COALESCE(custo_unit, 0) * 100.0) AS INTEGER)"
    )

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
    # apply_schema owns the outer transaction and foreign-key setting.
    if int(conn.execute("PRAGMA foreign_keys").fetchone()[0]):
        raise RuntimeError("A reconstrução do schema exige a transação de migração.")
    conn.execute("SAVEPOINT schema_rebuild")
    try:
        yield
        conn.execute("RELEASE SAVEPOINT schema_rebuild")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT schema_rebuild")
        conn.execute("RELEASE SAVEPOINT schema_rebuild")
        raise


def _validate_foreign_keys(conn: sqlite3.Connection) -> None:
    fk_enabled = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    if fk_enabled != 1:
        raise RuntimeError("PRAGMA foreign_keys está desligado após migração do schema")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Integridade relacional inválida após migração: {violations[:5]}")
