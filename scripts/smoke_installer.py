"""Install, upgrade and uninstall the Windows package in a disposable runner."""
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

from PIL import Image

from scripts.smoke_bundle import smoke_bundle


def shortcuts() -> dict[str, dict[str, str]]:
    script = r"""
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
    $shell = New-Object -ComObject WScript.Shell
    $result = @{}
    foreach ($kind in @('Desktop', 'Programs')) {
        $folder = [Environment]::GetFolderPath($kind)
        $link = Join-Path $folder 'SquackTS.lnk'
        $target = ''
        if (Test-Path -LiteralPath $link) { $target = $shell.CreateShortcut($link).TargetPath }
        $result[$kind] = @{ path = $link; target = $target }
    }
    $result | ConvertTo-Json -Compress
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8-sig", check=True, timeout=30,
    )
    return dict(json.loads(result.stdout))


def install(installer: Path, destination: Path, log: Path) -> None:
    subprocess.run(
        [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
         f"/DIR={destination}", f"/LOG={log}"],
        check=True, timeout=180,
    )


def fingerprint(home: Path) -> tuple[int, int, str, str]:
    with closing(sqlite3.connect(home / "data" / "pod_manager.db")) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Integridade invalida depois da instalacao/atualizacao")
        count, total = connection.execute("SELECT COUNT(*), COALESCE(SUM(total_cents), 0) FROM orders").fetchone()
        value = connection.execute("SELECT value FROM installer_smoke").fetchone()[0]
    digest = hashlib.sha256((home / "images" / "installer-smoke.png").read_bytes()).hexdigest()
    return int(count), int(total), str(value), digest


def smoke_installer(installer: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("O instalador deve ser testado num runner Windows descartavel")
    installer = installer.resolve(strict=True)
    if any(item["target"] for item in shortcuts().values()):
        raise RuntimeError("O perfil ja tem atalhos SquackTS; use um runner descartavel")
    with TemporaryDirectory(prefix="SquackTS installer test ") as directory:
        root = Path(directory)
        destination, home = root / "Installed app", root / "User data"
        executable = destination / "SquackTS.exe"
        uninstaller = destination / "unins000.exe"
        installed = False
        try:
            install(installer, destination, root / "install.log")
            installed = True
            for item in shortcuts().values():
                if Path(item["target"]).resolve() != executable.resolve():
                    raise RuntimeError(f"Atalho incorreto: {item['path']}")
            smoke_bundle(executable)
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = "offscreen"
            subprocess.run(
                [str(executable), "--demo", "--smoke-test", "--data-dir", str(home)],
                cwd=root, env=environment, check=True, timeout=60,
            )
            with closing(sqlite3.connect(home / "data" / "pod_manager.db")) as connection, connection:
                connection.execute("CREATE TABLE installer_smoke (value TEXT NOT NULL)")
                connection.execute("INSERT INTO installer_smoke VALUES ('preserved')")
            image = home / "images" / "installer-smoke.png"
            image.parent.mkdir(exist_ok=True)
            Image.new("RGBA", (2, 2), (30, 90, 180, 128)).save(image)
            before = fingerprint(home)
            if before[0] != 8:
                raise RuntimeError("Os dados de demonstracao nao foram criados")
            install(installer, destination, root / "upgrade.log")
            if fingerprint(home) != before:
                raise RuntimeError("A atualizacao alterou os dados do utilizador")
            subprocess.run(
                [str(executable), "--smoke-test", "--data-dir", str(home)],
                cwd=root, env=environment, check=True, timeout=60,
            )
            if fingerprint(home) != before:
                raise RuntimeError("O arranque depois da atualizacao alterou os dados")
            subprocess.run(
                [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                check=True, timeout=120,
            )
            installed = False
            if executable.exists() or any(item["target"] for item in shortcuts().values()):
                raise RuntimeError("A desinstalacao nao removeu a app/atalhos")
            if fingerprint(home) != before:
                raise RuntimeError("A desinstalacao removeu dados do utilizador")
            print("Instalador: instalacao, dois atalhos, arranque, reinstalacao e desinstalacao verificados; dados preservados.")
        finally:
            if installed and uninstaller.is_file():
                subprocess.run(
                    [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                    timeout=120, check=False,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    args = parser.parse_args()
    smoke_installer(args.installer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
