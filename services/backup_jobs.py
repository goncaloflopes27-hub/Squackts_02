"""Background backup work without sharing SQLite connections or Qt objects.

Future callbacks run on the executor thread (or immediately on the registering
thread when already complete). UI callers must marshal results through a queued
signal before touching widgets. Restore remains an exclusive application action.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import TypeVar

from config import AppPaths
from db import connect
from repositories.logs import LogRepository
from services.backup_service import BackupInspection, BackupService

_Result = TypeVar("_Result")


class BackupJobs:
    """Serialize disk-heavy jobs, opening and closing a connection per job.

    Call shutdown when the application closes. Pending tasks can be cancelled;
    an active backup is allowed to finish and close its own connection cleanly.
    The owner must prevent restore while busy, and prevent new jobs during it.
    """

    def __init__(self, paths: AppPaths, *, connection_factory: Callable[[Path], sqlite3.Connection] = connect) -> None:
        self.paths = paths
        self._connection_factory = connection_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="squackts-backup")
        self._lock = Lock()
        self._closed = False
        self._pending: set[Future[object]] = set()

    @property
    def busy(self) -> bool:
        with self._lock:
            return any(not pending.done() for pending in self._pending)

    def submit_backup(self) -> Future[Path]:
        return self._submit(lambda service: service.create_backup())

    def submit_inspection(self, path: Path | str) -> Future[BackupInspection]:
        backup_path = Path(path)
        return self._submit(lambda service: service.inspect_backup(backup_path))

    def _submit(self, operation: Callable[[BackupService], _Result]) -> Future[_Result]:
        with self._lock:
            if self._closed:
                raise RuntimeError("O executor de backups já foi encerrado.")
            future = self._executor.submit(self._execute, operation)
            # Track completion without inspecting result values.
            self._pending.add(future)
        future.add_done_callback(self._finished)
        return future

    def _finished(self, future: Future[_Result]) -> None:
        with self._lock:
            self._pending.discard(future)

    def _execute(self, operation: Callable[[BackupService], _Result]) -> _Result:
        if not self.paths.db_path.is_file():
            raise FileNotFoundError("A base de dados da aplicação ainda não foi inicializada.")
        # The factory, all SQL and close happen inside this worker, never UI.
        with closing(self._connection_factory(self.paths.db_path)) as conn:
            service = BackupService(
                conn,
                LogRepository(conn),
                self.paths.db_path,
                self.paths.backups_dir,
                self.paths.images_dir,
                self.paths.logs_dir,
            )
            return operation(service)

    def shutdown(self, *, wait: bool = False, cancel_futures: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __enter__(self) -> BackupJobs:
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown(wait=True)
