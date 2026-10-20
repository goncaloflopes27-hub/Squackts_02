# Build on the target operating system; PyInstaller does not cross-compile.
import sys
from pathlib import Path

project_root = Path(SPECPATH).parent
sys.path.insert(0, str(project_root))
from scripts.build_assets import generate_assets

assets = generate_assets()
analysis = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(assets / "build-info.json"), "."),
        (str(project_root / "packaging" / "assets" / "squackts.svg"), "assets"),
        (str(project_root / "ui" / "icons"), "ui/icons"),
    ],
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SquackTS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=sys.platform != "win32",
    icon=str(assets / "squackts.ico"),
    version=str(assets / "version.txt") if sys.platform == "win32" else None,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="SquackTS",
)

# Put human-facing instructions beside the executable rather than in _internal.
from shutil import copy2

distribution = Path(DISTPATH) / "SquackTS"
copy2(assets / "build-info.json", distribution / "build-info.json")
for document in ("README.md", "README.txt", "AGENTS.md", "PLANO_MELHORIAS.md", "RELATORIO_IMPLEMENTACAO.md", "criar_atalho_squackts.ps1"):
    copy2(project_root / document, distribution / document)
validation_dir = distribution / "docs"
validation_dir.mkdir(exist_ok=True)
copy2(project_root / "docs" / "VALIDACAO.md", validation_dir / "VALIDACAO.md")
copy2(project_root / "docs" / "REVISAO_EXTERNA.md", validation_dir / "REVISAO_EXTERNA.md")
