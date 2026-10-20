"""Small presentation files, read and written away from the Qt thread."""
from __future__ import annotations

import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

_pool: ThreadPoolExecutor | None = None


def submit_file(operation: str, path: Path, value: dict[str, Any] | None = None) -> Future[dict[str, Any]]:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="squackts-presentation")
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(shutdown_storage)
    return _pool.submit(_file_operation, operation, path, value)


def shutdown_storage() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=True)
        _pool = None


def _file_operation(operation: str, path: Path, value: dict[str, Any] | None) -> dict[str, Any]:
    if operation == "read":
        if not path.exists():
            return {}
        if path.stat().st_size > 1_000_000:
            raise ValueError("O ficheiro de apresentação excede o limite permitido.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("O ficheiro de apresentação é inválido.")
        return data
    if operation == "delete":
        path.unlink(missing_ok=True)
        return {}
    if operation != "write":
        raise ValueError("Operação de apresentação inválida.")
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".tmp")
    with staging.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path)
    return {}
