from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from config import AppPaths
from service_container import bootstrap_infrastructure


class SimulatedTermination(BaseException):
    pass


class RestoreInterruptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.paths = AppPaths.from_home(self.root / "current")
        self.current = bootstrap_infrastructure(self.paths, migrate_legacy=False)
        self.incoming = bootstrap_infrastructure(AppPaths.from_home(self.root / "incoming"), migrate_legacy=False)
        self.current.clients.create_client({"nome": "Original", "email": "original@example.test"})
        self.incoming.clients.create_client({"nome": "Incoming", "email": "incoming@example.test"})
        (self.current.images_dir / "original.txt").write_text("original")
        (self.incoming.images_dir / "incoming.txt").write_text("incoming")
        self.backup = self.incoming.backup.create_backup()

    def tearDown(self) -> None:
        self.current.close()
        self.incoming.close()
        self.directory.cleanup()

    def reopen(self) -> None:
        self.current.close()
        self.current = bootstrap_infrastructure(self.paths, migrate_legacy=False)

    def assert_original(self) -> None:
        self.assertEqual(self.current.clients.list_clients()[0]["nome"], "Original")
        self.assertEqual((self.current.images_dir / "original.txt").read_text(), "original")
        self.assertFalse((self.current.images_dir / "incoming.txt").exists())
        self.assertFalse(self.current.backup.restore_journal.exists())

    def test_termination_after_image_swap_recovers_before_opening_services(self) -> None:
        with patch.object(self.current.backup, "_replace_database", side_effect=SimulatedTermination):
            with self.assertRaises(SimulatedTermination):
                self.current.backup.restore_backup(self.backup)
        self.assertTrue(self.current.backup.restore_journal.is_file())
        self.reopen()
        self.assert_original()

    def test_termination_after_database_copy_recovers_both_resources(self) -> None:
        original = self.current.backup._replace_database

        def copy_then_terminate(path: Path) -> None:
            original(path)
            raise SimulatedTermination

        with patch.object(self.current.backup, "_replace_database", side_effect=copy_then_terminate):
            with self.assertRaises(SimulatedTermination):
                self.current.backup.restore_backup(self.backup)
        self.reopen()
        self.assert_original()

    def test_hard_process_exit_recovers_database_and_images_on_next_start(self) -> None:
        script = """
import os, sys
from pathlib import Path
from config import AppPaths
from service_container import bootstrap_infrastructure
container = bootstrap_infrastructure(AppPaths.from_home(Path(sys.argv[1])), migrate_legacy=False)
container.backup._replace_database = lambda path: os._exit(77)
container.backup.restore_backup(Path(sys.argv[2]))
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.paths.data_dir.parent), str(self.backup)], cwd=Path(__file__).resolve().parents[1], timeout=30)
        self.assertEqual(result.returncode, 77)
        self.assertTrue(self.current.backup.restore_journal.is_file())
        self.reopen()
        self.assert_original()

    def test_invalid_recovery_marker_does_not_change_data(self) -> None:
        journal = self.current.backup.restore_journal
        journal.write_text(json.dumps({"format": 1, "recovery": "../outside.zip", "sha256": ""}))
        with self.assertRaises(RuntimeError):
            self.current.backup.recover_interrupted_restore()
        self.assertEqual(self.current.clients.list_clients()[0]["nome"], "Original")
        self.assertEqual((self.current.images_dir / "original.txt").read_text(), "original")

    def test_windows_reserved_and_case_colliding_zip_paths_rejected(self) -> None:
        with zipfile.ZipFile(self.backup) as source:
            original = {name: source.read(name) for name in source.namelist()}
        for extra in ("images/CON.txt", "images/LPT1", "images/INCOMING.TXT", "images/trailing. "):
            with self.subTest(extra=extra):
                files = dict(original)
                files[extra] = b"content"
                manifest = json.loads(files["manifest.json"])
                manifest["files"][extra] = {"size": 7, "sha256": hashlib.sha256(b"content").hexdigest()}
                files["manifest.json"] = json.dumps(manifest).encode()
                candidate = self.root / "invalid.zip"
                with zipfile.ZipFile(candidate, "w") as target:
                    for name, content in files.items():
                        target.writestr(name, content)
                with self.assertRaises(ValueError):
                    self.current.backup.inspect_backup(candidate)

