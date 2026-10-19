from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from config import SCHEMA_USER_VERSION, AppPaths, application_data_home
from data_paths import migrate_legacy_data
from db import backup_database, connect
from repositories.logs import LogRepository
from schema import MIGRATIONS, SCHEMA_SQL, apply_schema
from services.backup_service import BackupService
from services.image_service import ImageService


def create_v3(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    return conn


def add_client(conn: sqlite3.Connection, name: str) -> int:
    cursor = conn.execute(
        "INSERT INTO clients(nome, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (name, f"{name}@example.test", "2026-01-01", "2026-01-01"),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def add_order(conn: sqlite3.Connection, client: int, state: str, paid: int, number: str) -> int:
    cursor = conn.execute(
        """INSERT INTO orders(numero, client_id, estado, pago, tracking,
        subtotal_cents, portes_cents, total_cents, created_at, updated_at)
        VALUES (?, ?, ?, ?, '', 120, 30, 150, '2026-01-01', '2026-01-01')""",
        (number, client, state, paid),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return cursor.lastrowid


class DataRecoveryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.connections: list[sqlite3.Connection] = []

    def tearDown(self) -> None:
        for conn in self.connections:
            conn.close()
        self.directory.cleanup()

    def database(self, name: str, *, legacy: bool = False) -> sqlite3.Connection:
        path = self.root / name / "data" / "pod_manager.db"
        conn = create_v3(path) if legacy else connect(path)
        self.connections.append(conn)
        if not legacy:
            apply_schema(conn)
        return conn

    def service(self, name: str) -> BackupService:
        conn = self.database(name)
        home = self.root / name
        images = home / "images"
        images.mkdir()
        return BackupService(
            conn, LogRepository(conn), home / "data" / "pod_manager.db", home / "backups", images, home / "logs"
        )

    def test_data_home_override_and_os_defaults(self) -> None:
        override = self.root / "custom"
        with patch.dict(os.environ, {"SQUACKTS_DATA_HOME": str(override)}):
            self.assertEqual(application_data_home(), override)
        with (
            patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "xdg")}, clear=True),
            patch("config.sys.platform", "linux"),
        ):
            self.assertEqual(application_data_home(), self.root / "xdg" / "squackts")
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "windows")}, clear=True),
            patch("config.sys.platform", "win32"),
        ):
            self.assertEqual(application_data_home(), self.root / "windows" / "Squackts")
        self.assertEqual(AppPaths.from_home(override).db_path, override / "data" / "pod_manager.db")

    def test_legacy_copy_preserves_source_and_committed_wal(self) -> None:
        source = self.database("checkout", legacy=True)
        add_client(source, "legacy")
        old_images = self.root / "checkout" / "assets" / "images"
        old_images.mkdir(parents=True)
        (old_images / "example.png").write_bytes(b"image payload")
        original_reference = str(old_images / "example.png")
        source.execute(
            """INSERT INTO products(sku,nome,preco_cents,custo_cents,tipo_producao,image_path,created_at,updated_at)
            VALUES ('P1','Legacy',100,50,'print_on_demand',?,'2026-01-01','2026-01-01')""",
            (original_reference,),
        )
        source.commit()
        old_backups = self.root / "checkout" / "backups"
        old_backups.mkdir()
        (old_backups / "retained.sqlite3").write_bytes(b"historical backup")
        paths = AppPaths.from_home(self.root / "user-data", base_dir=self.root / "checkout")
        self.assertTrue(migrate_legacy_data(paths))
        with closing(sqlite3.connect(paths.db_path)) as copied:
            self.assertEqual(copied.execute("SELECT nome FROM clients").fetchone()[0], "legacy")
            self.assertEqual(copied.execute("SELECT image_path FROM products").fetchone()[0], "example.png")
        self.assertEqual(source.execute("SELECT nome FROM clients").fetchone()[0], "legacy")
        self.assertEqual(source.execute("SELECT image_path FROM products").fetchone()[0], original_reference)
        self.assertEqual((paths.backups_dir / "retained.sqlite3").read_bytes(), b"historical backup")
        self.assertEqual((paths.images_dir / "example.png").read_bytes(), b"image payload")
        self.assertFalse(migrate_legacy_data(paths))

    def test_legacy_conflict_never_overwrites_user_images_or_source(self) -> None:
        self.database("checkout", legacy=True)
        old_images = self.root / "checkout" / "assets" / "images"
        old_images.mkdir(parents=True)
        (old_images / "same.png").write_bytes(b"old")
        paths = AppPaths.from_home(self.root / "destination", base_dir=self.root / "checkout")
        paths.images_dir.mkdir(parents=True)
        (paths.images_dir / "same.png").write_bytes(b"new")
        with self.assertRaisesRegex(ValueError, "conflito"):
            migrate_legacy_data(paths)
        self.assertFalse(paths.db_path.exists())
        self.assertEqual((paths.images_dir / "same.png").read_bytes(), b"new")

    def test_payment_migration_preserves_flags_and_reports_contradictions(self) -> None:
        conn = self.database("legacy", legacy=True)
        client = add_client(conn, "legacy")
        good = add_order(conn, client, "paga", 1, "ENC-1")
        wrong = add_order(conn, client, "paga", 0, "ENC-2")
        shipped = add_order(conn, client, "expedida", 1, "ENC-3")
        apply_schema(conn)
        row = conn.execute(
            "SELECT estado, pago, total_cents, payment_recorded_at FROM orders WHERE id=?", (good,)
        ).fetchone()
        self.assertEqual(tuple(row), ("confirmada", 1, 150, ""))
        self.assertEqual(
            tuple(conn.execute("SELECT estado, pago FROM orders WHERE id=?", (wrong,)).fetchone()), ("confirmada", 0)
        )
        self.assertEqual(
            {row[0] for row in conn.execute("SELECT order_id FROM reconciliation_issues")}, {wrong, shipped}
        )
        snapshots = list((self.root / "legacy" / "data" / "migration_backups").glob("*.sqlite3"))
        self.assertEqual(len(snapshots), 1)
        with closing(sqlite3.connect(snapshots[0])) as before:
            self.assertEqual(before.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(before.execute("SELECT estado FROM orders WHERE id=?", (good,)).fetchone()[0], "paga")
        apply_schema(conn)
        self.assertEqual(len(list(snapshots[0].parent.glob("*.sqlite3"))), 1)

    def test_failed_migration_rolls_back_all_steps_and_keeps_recovery(self) -> None:
        conn = self.database("legacy", legacy=True)
        add_client(conn, "preserved")

        def fail(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM clients")
            raise RuntimeError("injected migration failure")

        with patch.dict(MIGRATIONS, {5: fail}), self.assertRaisesRegex(RuntimeError, "injected"):
            apply_schema(conn)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertEqual(conn.execute("SELECT nome FROM clients").fetchone()[0], "preserved")
        self.assertNotIn("payment_recorded_at", {row[1] for row in conn.execute("PRAGMA table_info(orders)")})
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertTrue(list((self.root / "legacy" / "data" / "migration_backups").glob("*.sqlite3")))

    def test_early_numbered_schemas_also_migrate_legacy_money(self) -> None:
        for version in (1, 2):
            with self.subTest(version=version), closing(sqlite3.connect(":memory:")) as conn:
                conn.execute("""CREATE TABLE products (
                    id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, nome TEXT NOT NULL,
                    descricao TEXT NOT NULL DEFAULT '', preco REAL NOT NULL, custo REAL NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 0, stock_minimo INTEGER NOT NULL DEFAULT 0,
                    tipo_producao TEXT NOT NULL, image_path TEXT NOT NULL DEFAULT '',
                    ativo INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
                conn.execute("""INSERT INTO products(id, sku, nome, preco, custo, tipo_producao, created_at, updated_at)
                    VALUES (42, 'OLD-42', 'Legacy', 12.25, 3.50, 'dtg', '2026-01-01', '2026-01-01')""")
                conn.execute(f"PRAGMA user_version = {version}")
                conn.commit()
                apply_schema(conn)
                self.assertEqual(
                    conn.execute(
                        "SELECT id, preco_cents, custo_cents, tipo_producao, technique FROM products"
                    ).fetchone(),
                    (42, 1225, 350, "print_on_demand", "dtg"),
                )
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_USER_VERSION)
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_legacy_technique_survives_rebuild_and_failed_migration_rolls_it_back(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.connections.append(conn)
        conn.executescript(
            SCHEMA_SQL.replace("'print_on_demand', 'stock_fisico', 'misto'", "'DTF', 'stock_fisico', 'misto'")
        )
        conn.execute("""INSERT INTO products(sku,nome,preco_cents,custo_cents,tipo_producao,created_at,updated_at)
            VALUES ('DTF1','T-shirt',100,50,'DTF','','')""")
        conn.commit()

        def fail(connection: sqlite3.Connection) -> None:
            raise RuntimeError("injected failure after normalization")

        with patch.dict(MIGRATIONS, {5: fail}), self.assertRaisesRegex(RuntimeError, "injected"):
            apply_schema(conn)
        self.assertEqual(conn.execute("SELECT tipo_producao, technique FROM products").fetchone(), ("DTF", ""))
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)
        apply_schema(conn)
        self.assertEqual(
            conn.execute("SELECT tipo_producao, technique FROM products").fetchone(), ("print_on_demand", "DTF")
        )

    def test_version_five_gets_numbered_query_index_migration(self) -> None:
        conn = self.database("version-five")
        add_client(conn, "preserved")
        indexes = {
            "idx_orders_created",
            "idx_orders_state_created",
            "idx_orders_client_created",
            "idx_orders_updated",
            "idx_orders_state_updated",
            "idx_logs_entity",
        }
        for name in indexes:
            conn.execute(f"DROP INDEX IF EXISTS {name}")
        conn.execute("PRAGMA user_version=5")
        conn.commit()
        apply_schema(conn)
        created = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertTrue(indexes.issubset(created))
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM orders WHERE estado='confirmada' ORDER BY created_at DESC, id DESC LIMIT 50"
        ).fetchall()
        self.assertTrue(any("idx_orders_state_created" in str(tuple(row)) for row in plan))
        self.assertEqual(conn.execute("SELECT nome FROM clients").fetchone()[0], "preserved")
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_USER_VERSION)

    def test_newer_schema_is_refused_without_downgrade(self) -> None:
        conn = self.database("future")
        add_client(conn, "preserved")
        conn.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION + 1}")
        with self.assertRaisesRegex(RuntimeError, "mais recente"):
            apply_schema(conn)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_USER_VERSION + 1)
        self.assertEqual(conn.execute("SELECT nome FROM clients").fetchone()[0], "preserved")

    def test_complete_backup_restores_wal_database_and_managed_images(self) -> None:
        source = self.service("source")
        add_client(source.conn, "snapshot")
        image = self.root / "outside.png"
        Image.new("RGB", (600, 300), "red").save(image)
        imported = ImageService(source.images_dir).import_image(image)
        backup = source.create_backup()
        self.assertEqual(source.inspect_backup(backup).image_count, 2)
        destination = self.service("destination")
        add_client(destination.conn, "replace-me")
        (destination.images_dir / "old.txt").write_text("old image")
        result = destination.restore_backup(backup)
        self.assertTrue(result.restart_required)
        self.assertTrue(result.recovery_backup.exists())
        self.assertEqual(destination.conn.execute("SELECT nome FROM clients").fetchone()[0], "snapshot")
        self.assertFalse((destination.images_dir / "old.txt").exists())
        self.assertEqual(
            (source.images_dir / imported.image_path).read_bytes(),
            (destination.images_dir / imported.image_path).read_bytes(),
        )
        with Image.open(destination.images_dir / imported.thumbnail_path) as thumb:
            self.assertEqual(thumb.size, (320, 160))
        self.assertTrue(destination.get_diagnostics().integrity_ok)
        # The recovery package holds precisely the pre-restore database and files.
        recovered = self.service("recovered")
        recovered.restore_backup(result.recovery_backup)
        self.assertEqual(recovered.conn.execute("SELECT nome FROM clients").fetchone()[0], "replace-me")
        self.assertEqual((recovered.images_dir / "old.txt").read_text(), "old image")

    def test_old_sqlite_backup_restores_and_retains_current_images(self) -> None:
        source = self.database("legacy", legacy=True)
        add_client(source, "legacy")
        backup = backup_database(source, self.root / "sqlite-backups")
        destination = self.service("destination")
        (destination.images_dir / "retained.png").write_bytes(b"existing")
        destination.restore_backup(backup)
        self.assertEqual(destination.conn.execute("SELECT nome FROM clients").fetchone()[0], "legacy")
        self.assertEqual(destination.conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_USER_VERSION)
        self.assertEqual((destination.images_dir / "retained.png").read_bytes(), b"existing")

    def test_corrupt_checksum_and_traversal_backups_leave_current_data_untouched(self) -> None:
        service = self.service("source")
        add_client(service.conn, "safe")
        backup = service.create_backup()
        damaged = self.root / "damaged.zip"
        with zipfile.ZipFile(backup) as original, zipfile.ZipFile(damaged, "w") as changed:
            for entry in original.infolist():
                payload = original.read(entry)
                if entry.filename == "database.sqlite3":
                    payload += b"tampered"
                changed.writestr(entry.filename, payload)
        with self.assertRaisesRegex(ValueError, "verifica"):
            service.restore_backup(damaged)
        traversal = self.root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("../escape", b"bad")
        with self.assertRaisesRegex(ValueError, "caminho"):
            service.restore_backup(traversal)
        self.assertFalse((self.root / "escape").exists())
        self.assertEqual(service.conn.execute("SELECT nome FROM clients").fetchone()[0], "safe")
        self.assertEqual(len(service.list_backups()), 1)

    def test_database_corruption_and_future_backup_are_rejected(self) -> None:
        destination = self.service("destination")
        add_client(destination.conn, "safe")
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not a database")
        with self.assertRaises(ValueError):
            destination.restore_backup(corrupt)
        future = self.database("future")
        future.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION + 1}")
        future_path = backup_database(future, self.root / "future-backups")
        with self.assertRaisesRegex(ValueError, "versão"):
            destination.restore_backup(future_path)
        self.assertEqual(destination.conn.execute("SELECT nome FROM clients").fetchone()[0], "safe")

    def test_failure_after_database_replacement_recovers_database_and_images(self) -> None:
        source = self.service("source")
        add_client(source.conn, "incoming")
        (source.images_dir / "incoming.png").write_bytes(b"incoming")
        incoming = source.create_backup()
        destination = self.service("destination")
        add_client(destination.conn, "original")
        (destination.images_dir / "original.png").write_bytes(b"original")
        replace = destination._replace_database
        attempts = 0

        def fail_once(path: Path) -> None:
            nonlocal attempts
            attempts += 1
            replace(path)
            if attempts == 1:
                raise OSError("simulated device error after replacement")

        with (
            patch.object(destination, "_replace_database", side_effect=fail_once),
            self.assertRaisesRegex(RuntimeError, "recuperados"),
        ):
            destination.restore_backup(incoming)
        self.assertEqual(destination.conn.execute("SELECT nome FROM clients").fetchone()[0], "original")
        self.assertEqual((destination.images_dir / "original.png").read_bytes(), b"original")
        self.assertFalse((destination.images_dir / "incoming.png").exists())
        self.assertEqual(len(destination.list_backups()), 1)
        self.assertTrue(destination.get_diagnostics().integrity_ok)

    def test_image_import_survives_source_removal_and_rejects_invalid_inputs(self) -> None:
        service = ImageService(self.root / "managed")
        source = self.root / "image.png"
        Image.new("RGBA", (50, 25), (40, 100, 80, 128)).save(source)
        first = service.import_image(source)
        self.assertEqual(first, service.import_image(source))
        source.unlink()
        with Image.open(service.resolve(first.image_path)) as image:
            self.assertEqual(image.size, (50, 25))
        with self.assertRaises(ValueError):
            service.resolve("../outside.png")
        bad = self.root / "bad.png"
        bad.write_bytes(b"bad image")
        with self.assertRaisesRegex(ValueError, "válido"):
            service.import_image(bad)


if __name__ == "__main__":
    unittest.main()
