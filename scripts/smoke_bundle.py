"""Open the frozen app twice from outside its folder and verify persistence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory


def smoke_bundle(executable: Path, screenshots: Path | None = None, *, platform: str | None = None) -> None:
    executable = executable.resolve(strict=True)
    platform = platform or ("windows" if sys.platform == "win32" else "offscreen")
    if platform == "windows" and not list((executable.parent / "_internal").rglob("qwindows.dll")):
        raise RuntimeError("O plugin qwindows.dll está ausente da distribuição")
    source_icons = Path(__file__).resolve().parents[1] / "ui" / "icons"
    for page in ("dashboard", "orders", "products", "clients", "production", "system"):
        icon_name = f"nav-{page}.svg"
        packaged = executable.parent / "_internal" / "ui" / "icons" / icon_name
        if not packaged.is_file():
            raise RuntimeError(f"Ícone de navegação ausente na distribuição: {icon_name}")
        if hashlib.sha256(packaged.read_bytes()).digest() != hashlib.sha256((source_icons / icon_name).read_bytes()).digest():
            raise RuntimeError(f"Ícone de navegação desatualizado: {icon_name}")
    with TemporaryDirectory(prefix="squackts-bundle-") as directory:
        home = Path(directory) / "user-data"
        environment = os.environ.copy()
        environment.update(SQUACKTS_DATA_HOME=str(home), QT_QPA_PLATFORM=platform)
        for attempt in range(2):
            command = [str(executable), "--smoke-test", "--data-dir", str(home), "--expect-platform", platform]
            if screenshots is not None:
                command.extend(["--screenshots", str((screenshots / str(attempt + 1)).resolve())])
            subprocess.run(
                command,
                cwd=directory, env=environment, check=True, timeout=60,
            )
            if screenshots is not None:
                report = json.loads((screenshots / str(attempt + 1) / "smoke-report.json").read_text(encoding="utf-8"))
                metadata = json.loads((executable.parent / "build-info.json").read_text(encoding="utf-8"))
                if report["platform"] != platform or report["version"] != metadata["release_version"]:
                    raise RuntimeError("O plugin/versão em execução não coincide com o pacote")
            database = home / "data" / "pod_manager.db"
            if not database.is_file():
                raise RuntimeError("O executável não criou a base no diretório do utilizador")
            with closing(sqlite3.connect(database)) as connection, connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Integridade da base inválida")
                if attempt == 0:
                    connection.execute("CREATE TABLE distribution_smoke (value TEXT NOT NULL)")
                    connection.execute("INSERT INTO distribution_smoke VALUES (?)", ("persisted",))
                elif connection.execute("SELECT value FROM distribution_smoke").fetchone()[0] != "persisted":
                    raise RuntimeError("Dados não preservados no segundo arranque")
        print(f"Bundle: dois arranques, Qt {platform}, seis ícones de navegação e persistência verificados.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", type=Path, default=Path("dist/SquackTS") / ("SquackTS.exe" if sys.platform == "win32" else "SquackTS"))
    parser.add_argument("--screenshots", type=Path, help="Guardar capturas dos dois arranques")
    parser.add_argument("--platform", help="Plugin Qt a carregar e verificar")
    args = parser.parse_args()
    smoke_bundle(args.executable, args.screenshots, platform=args.platform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
