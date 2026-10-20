from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import CancelledError
from pathlib import Path
from unittest.mock import patch

from config import AppPaths
from db import connect
from schema import apply_schema
from services.backup_jobs import BackupJobs
from services.backup_service import BackupService


class TrackedConnection(sqlite3.Connection):
    creator_thread: int = 0
    closer_thread: int = 0
    closed: bool = False

    def close(self) -> None:
        self.closer_thread = threading.get_ident()
        super().close()
        self.closed = True


class BackgroundJobsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.paths = AppPaths.from_home(Path(self.directory.name))
        conn = connect(self.paths.db_path)
        try:
            apply_schema(conn)
            conn.execute(
                "INSERT INTO clients(nome,email,created_at,updated_at) VALUES ('Background','bg@example.test','','')"
            )
            conn.commit()
        finally:
            conn.close()
        self.connections: list[TrackedConnection] = []
        self.runners: list[BackupJobs] = []

    def tearDown(self) -> None:
        for runner in self.runners:
            runner.shutdown(wait=True)
        self.directory.cleanup()

    def runner(self) -> BackupJobs:
        def factory(path: Path) -> sqlite3.Connection:
            conn = sqlite3.connect(path, factory=TrackedConnection)
            conn.creator_thread = threading.get_ident()
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            self.connections.append(conn)
            return conn

        runner = BackupJobs(self.paths, connection_factory=factory)
        self.runners.append(runner)
        return runner

    def test_backup_and_inspection_use_fresh_worker_connections_and_close_them(self) -> None:
        runner = self.runner()
        backup = runner.submit_backup().result(timeout=5)
        inspected = runner.submit_inspection(backup).result(timeout=5)
        self.assertEqual(inspected.format, "zip")
        self.assertTrue(backup.is_file())
        self.assertFalse(runner.busy)
        self.assertEqual(len(self.connections), 2)
        self.assertIsNot(self.connections[0], self.connections[1])
        for conn in self.connections:
            self.assertNotEqual(conn.creator_thread, threading.get_ident())
            self.assertEqual(conn.closer_thread, conn.creator_thread)
            self.assertTrue(conn.closed)
        # A separate main-thread connection observes the committed backup log.
        conn = connect(self.paths.db_path)
        try:
            self.assertEqual(conn.execute("SELECT count(*) FROM logs WHERE acao='backup_created'").fetchone()[0], 1)
        finally:
            conn.close()

    def test_failure_reaches_future_closes_connection_and_next_job_still_runs(self) -> None:
        runner = self.runner()
        with patch.object(BackupService, "create_backup", side_effect=OSError("simulated full disk")):
            failed = runner.submit_backup()
            with self.assertRaisesRegex(OSError, "full disk"):
                failed.result(timeout=5)
        self.assertTrue(self.connections[0].closed)
        backup = runner.submit_backup().result(timeout=5)
        self.assertTrue(backup.exists())
        self.assertTrue(all(conn.closed for conn in self.connections))

    def test_shutdown_cancels_queued_jobs_and_allows_active_job_to_close(self) -> None:
        runner = self.runner()
        entered = threading.Event()
        release = threading.Event()
        real_create = BackupService.create_backup

        def blocked(service: BackupService) -> Path:
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test did not release backup")
            return real_create(service)

        with patch.object(BackupService, "create_backup", blocked):
            active = runner.submit_backup()
            self.assertTrue(entered.wait(timeout=5))
            queued = runner.submit_backup()
            self.assertTrue(runner.busy)
            runner.shutdown(wait=False, cancel_futures=True)
            try:
                with self.assertRaises(CancelledError):
                    queued.result(timeout=1)
                with self.assertRaisesRegex(RuntimeError, "encerrado"):
                    runner.submit_backup()
            finally:
                release.set()
            self.assertTrue(active.result(timeout=5).exists())
        self.assertEqual(len(self.connections), 1)
        self.assertTrue(self.connections[0].closed)
        self.assertFalse(runner.busy)

    def test_inspection_error_does_not_leak_connection(self) -> None:
        runner = self.runner()
        with self.assertRaisesRegex(ValueError, "não existe"):
            runner.submit_inspection(Path(self.directory.name) / "missing.zip").result(timeout=5)
        self.assertTrue(self.connections[0].closed)
        self.assertFalse(runner.busy)

    def test_missing_database_does_not_create_an_empty_database(self) -> None:
        missing = AppPaths.from_home(Path(self.directory.name) / "missing")
        runner = BackupJobs(missing)
        self.runners.append(runner)
        with self.assertRaises(FileNotFoundError):
            runner.submit_backup().result(timeout=5)
        self.assertFalse(missing.db_path.exists())


if __name__ == "__main__":
    unittest.main()
