"""Additive, transactional POD and inventory schema migration.

The caller owns the transaction and schema version. Existing deducted stock is
adopted as a reservation, preserving the available amount shown to the operator.
"""

from __future__ import annotations

import sqlite3


def _add_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def apply_pod_schema(conn: sqlite3.Connection) -> None:
    _add_column(conn, "products", "technique", "TEXT NOT NULL DEFAULT ''")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            sku TEXT NOT NULL UNIQUE, tamanho TEXT NOT NULL DEFAULT '', cor TEXT NOT NULL DEFAULT '',
            preco_cents INTEGER NOT NULL CHECK(preco_cents >= 0),
            custo_cents INTEGER NOT NULL CHECK(custo_cents >= 0),
            stock_on_hand INTEGER NOT NULL DEFAULT 0 CHECK(stock_on_hand >= 0),
            stock_reserved INTEGER NOT NULL DEFAULT 0 CHECK(stock_reserved >= 0 AND stock_reserved <= stock_on_hand),
            ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
            is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_variants_default ON product_variants(product_id) WHERE is_default=1"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_variants_product ON product_variants(product_id)")
    for name, definition in (
        ("variant_id", "INTEGER REFERENCES product_variants(id) ON DELETE RESTRICT"),
        ("personalization", "TEXT NOT NULL DEFAULT ''"),
        ("artwork_path", "TEXT NOT NULL DEFAULT ''"),
        ("technique_snapshot", "TEXT NOT NULL DEFAULT ''"),
    ):
        _add_column(conn, "order_items", name, definition)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_allocations (
            order_item_id INTEGER PRIMARY KEY REFERENCES order_items(id) ON DELETE CASCADE,
            variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
            reserved_quantity INTEGER NOT NULL CHECK(reserved_quantity >= 0),
            production_quantity INTEGER NOT NULL CHECK(production_quantity >= 0),
            status TEXT NOT NULL CHECK(status IN ('reserved','consumed','released')),
            legacy INTEGER NOT NULL DEFAULT 0 CHECK(legacy IN (0,1)),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
            order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
            order_item_id INTEGER REFERENCES order_items(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            on_hand_delta INTEGER NOT NULL DEFAULT 0,
            reserved_delta INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movements_variant ON inventory_movements(variant_id, id)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_item_id INTEGER NOT NULL UNIQUE REFERENCES order_items(id) ON DELETE CASCADE,
            quantity INTEGER NOT NULL CHECK(quantity > 0), technique TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','em_producao','concluida')),
            art_required INTEGER NOT NULL DEFAULT 0 CHECK(art_required IN (0,1)),
            art_approved INTEGER NOT NULL DEFAULT 0 CHECK(art_approved IN (0,1)),
            artwork_reference TEXT NOT NULL DEFAULT '',
            qc_required INTEGER NOT NULL DEFAULT 1 CHECK(qc_required IN (0,1)),
            qc_approved INTEGER NOT NULL DEFAULT 0 CHECK(qc_approved IN (0,1)),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        INSERT INTO product_variants
            (product_id,sku,preco_cents,custo_cents,stock_on_hand,ativo,is_default,created_at,updated_at)
        SELECT p.id,p.sku,p.preco_cents,p.custo_cents,p.stock,p.ativo,1,p.created_at,p.updated_at
        FROM products p WHERE NOT EXISTS
            (SELECT 1 FROM product_variants v WHERE v.product_id=p.id AND v.is_default=1)
    """)
    conn.execute("""INSERT INTO inventory_movements
        (variant_id,kind,on_hand_delta,reserved_delta,reason,created_at)
        SELECT v.id,'opening',v.stock_on_hand,0,'Saldo inicial migrado',v.created_at
        FROM product_variants v WHERE NOT EXISTS
            (SELECT 1 FROM inventory_movements m WHERE m.variant_id=v.id)
    """)
    conn.execute("""
        UPDATE order_items SET variant_id=(SELECT id FROM product_variants
        WHERE product_id=order_items.product_id AND is_default=1) WHERE variant_id IS NULL
    """)
    # Deducted legacy goods remain physically present until dispatch. Add them
    # back to physical *and* reserved stock, so available stock never changes.
    legacy_items = conn.execute("""
        SELECT oi.id,oi.order_id,oi.variant_id,oi.quantidade,o.estado,o.updated_at
        FROM order_items oi JOIN orders o ON o.id=oi.order_id
        WHERE oi.stock_deducted=1 AND oi.stock_returned=0 AND NOT EXISTS
            (SELECT 1 FROM inventory_allocations a WHERE a.order_item_id=oi.id)
    """).fetchall()
    for item in legacy_items:
        item_id, order_id, variant_id, quantity, state, updated_at = item
        active = state not in {"expedida", "concluida", "cancelada"}
        if active:
            conn.execute(
                "UPDATE product_variants SET stock_on_hand=stock_on_hand+?,stock_reserved=stock_reserved+? WHERE id=?",
                (quantity, quantity, variant_id),
            )
        conn.execute(
            """INSERT INTO inventory_allocations
            (order_item_id,variant_id,reserved_quantity,production_quantity,status,legacy,created_at,updated_at)
            VALUES (?,?,?,0,?,1,?,?)""",
            (
                item_id,
                variant_id,
                quantity,
                "reserved" if active else ("released" if state == "cancelada" else "consumed"),
                updated_at,
                updated_at,
            ),
        )
        conn.execute(
            """INSERT INTO inventory_movements
            (variant_id,order_id,order_item_id,kind,on_hand_delta,reserved_delta,reason,created_at)
            VALUES (?,?,?,'legacy_adoption',?,?,?,?)""",
            (
                variant_id,
                order_id,
                item_id,
                quantity if active else 0,
                quantity if active else 0,
                "Stock já descontado no sistema anterior; disponibilidade preservada",
                updated_at,
            ),
        )

    # Existing mixed orders with insufficient stock used to produce the entire
    # quantity. Keep that historical allocation; only new confirmations use
    # partial stock. Already completed production remains completed.
    conn.execute("""INSERT INTO inventory_allocations
        (order_item_id,variant_id,reserved_quantity,production_quantity,status,legacy,created_at,updated_at)
        SELECT oi.id,oi.variant_id,0,oi.quantidade,
            CASE WHEN o.estado IN ('expedida','concluida') THEN 'consumed' ELSE 'reserved' END,
            1,o.created_at,o.updated_at
        FROM order_items oi JOIN orders o ON o.id=oi.order_id
        WHERE o.estado IN ('confirmada','em_producao','pronta_envio','expedida','concluida')
            AND oi.stock_deducted=0 AND NOT EXISTS
                (SELECT 1 FROM inventory_allocations a WHERE a.order_item_id=oi.id)
    """)
    conn.execute("""INSERT INTO production_tasks
        (order_item_id,quantity,technique,status,qc_approved,created_at,updated_at,completed_at)
        SELECT oi.id,a.production_quantity,oi.technique_snapshot,
            CASE WHEN o.estado IN ('pronta_envio','expedida','concluida') THEN 'concluida' ELSE 'pendente' END,
            CASE WHEN o.estado IN ('pronta_envio','expedida','concluida') THEN 1 ELSE 0 END,
            o.created_at,o.updated_at,
            CASE WHEN o.estado IN ('pronta_envio','expedida','concluida') THEN o.updated_at ELSE '' END
        FROM inventory_allocations a JOIN order_items oi ON oi.id=a.order_item_id
        JOIN orders o ON o.id=oi.order_id
        WHERE a.legacy=1 AND a.production_quantity>0 AND NOT EXISTS
            (SELECT 1 FROM production_tasks t WHERE t.order_item_id=oi.id)
    """)
