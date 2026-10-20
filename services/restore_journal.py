"""Durable intent: incomplete DB/image restores revert before opening the UI."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def begin_restore(journal: Path, recovery: Path) -> None:
    content = {"format": 1, "recovery": recovery.name, "sha256": file_digest(recovery)}
    temporary = journal.with_name(f".restore-intent-{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(content, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, journal)
    finally:
        temporary.unlink(missing_ok=True)


def pending_recovery(journal: Path, backups_dir: Path) -> Path | None:
    if not journal.exists():
        return None
    try:
        if journal.is_symlink() or journal.stat().st_size > 4096:
            raise ValueError("Marcador de restauro inválido")
        content = json.loads(journal.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or content.get("format") != 1:
            raise ValueError("Marcador de restauro inválido")
        name = content.get("recovery")
        if not isinstance(name, str) or not name or Path(name).name != name or any(c in name for c in ('/', '\\', ':')):
            raise ValueError("Caminho de recuperação inválido")
        recovery = backups_dir / name
        if recovery.is_symlink() or not recovery.is_file() or file_digest(recovery) != content.get("sha256"):
            raise ValueError("A cópia de recuperação está ausente ou foi alterada")
        return recovery
    except (OSError, ValueError) as error:
        raise RuntimeError("Foi detetado um restauro interrompido, mas a cópia de recuperação não pôde ser validada. Preserve esta pasta e os backups.") from error
