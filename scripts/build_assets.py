"""Generate Windows icon/version resources from the checked-in SVG and version."""
from __future__ import annotations

import ast
import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def app_version() -> str:
    tree = ast.parse((ROOT / "config.py").read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            if statement.target.id == "APP_VERSION":
                return str(ast.literal_eval(statement.value))
    raise RuntimeError("APP_VERSION não encontrada em config.py")


def generate_assets() -> Path:
    target = ROOT / "build" / "assets"
    target.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(ROOT / "packaging" / "assets" / "squackts.svg"))
    if not renderer.isValid():
        raise RuntimeError("Ícone SVG inválido")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    image_data = QByteArray()
    buffer = QBuffer(image_data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Não foi possível converter o ícone")
    buffer.close()
    with Image.open(io.BytesIO(bytes(image_data))) as source:
        source.save(target / "squackts.ico", sizes=[(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)])
    version = app_version()
    numbers = tuple(int(part) for part in version.split("."))
    version_tuple = (numbers + (0, 0, 0, 0))[:4]
    (target / "version.txt").write_text(
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={version_tuple!r}, prodvers={version_tuple!r}, "
        "mask=0x3f, flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),\n"
        "  kids=[StringFileInfo([StringTable('081604B0', [\n"
        "    StringStruct('CompanyName', 'Squack TS'),\n"
        "    StringStruct('ProductName', 'SquackTS'),\n"
        "    StringStruct('FileDescription', 'Gestão local de Print-on-Demand'),\n"
        f"    StringStruct('FileVersion', {version!r}),\n"
        f"    StringStruct('ProductVersion', {version!r}),\n"
        "    StringStruct('OriginalFilename', 'SquackTS.exe')\n"
        "  ])]), VarFileInfo([VarStruct('Translation', [2070, 1200])])]\n"
        ")\n",
        encoding="utf-8",
    )
    return target


if __name__ == "__main__":
    print(generate_assets())
