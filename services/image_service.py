from __future__ import annotations

import hashlib
import io
import os
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True, slots=True)
class ManagedImage:
    image_path: str
    thumbnail_path: str
    width: int
    height: int


class ImageService:
    """Import decoded images into immutable, content-addressed application assets."""

    def __init__(self, images_dir: Path) -> None:
        self.images_dir = images_dir

    def resolve(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if not relative.parts or relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
            raise ValueError("Referência de imagem inválida.")
        candidate = (self.images_dir / relative).resolve()
        if not candidate.is_relative_to(self.images_dir.resolve()):
            raise ValueError("Imagem fora da pasta gerida.")
        return candidate

    def import_image(self, source: Path | str) -> ManagedImage:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source) as image:
                    if image.width * image.height > 40_000_000:
                        raise ValueError("A imagem excede o limite de 40 megapíxeis.")
                    image.load()
                    has_alpha = "A" in image.getbands() or "transparency" in image.info
                    normalized = ImageOps.exif_transpose(image).convert("RGBA" if has_alpha else "RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("Escolha um ficheiro de imagem válido e suportado.") from exc
        content = io.BytesIO()
        normalized.save(content, format="PNG")
        image_bytes = content.getvalue()
        identity = hashlib.sha256(image_bytes).hexdigest()
        image_path = f"originals/{identity}.png"
        thumbnail_path = f"thumbnails/{identity}.png"
        thumbnail = normalized.copy()
        thumbnail.thumbnail((320, 320), Image.Resampling.LANCZOS)
        content = io.BytesIO()
        thumbnail.save(content, format="PNG")
        self._write(image_path, image_bytes)
        self._write(thumbnail_path, content.getvalue())
        return ManagedImage(image_path, thumbnail_path, normalized.width, normalized.height)

    def _write(self, relative: str, content: bytes) -> None:
        destination = self.resolve(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != content:
                raise ValueError("O ficheiro de imagem gerido não passou a verificação de integridade.")
            return
        handle, temporary = tempfile.mkstemp(prefix=".image-", dir=destination.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
