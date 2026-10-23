"""Adapter de volume privado: chaves UUID, publicação atômica e sem sobrescrita."""

import hashlib
import io
import os
import tempfile
import warnings
from pathlib import Path
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from rotalog.core.config import Settings
from rotalog.core.contracts import fail


class PrivateImageStorage:
    def __init__(self, settings: Settings):
        self.root = settings.product_images_root.resolve()
        self.limit = settings.product_image_max_bytes

    def _path(self, run_id: UUID, file_id: UUID) -> Path:
        # Nenhum nome, extensão ou path enviado pelo cliente participa desta chave.
        return self.root / run_id.hex / file_id.hex

    def read(self, run_id: UUID, file_id: UUID) -> bytes:
        path = self._path(run_id, file_id)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            data = stream.read(self.limit + 1)
        if len(data) > self.limit:
            fail("FILE_SIZE_INVALID", "Arquivo excede o limite autorizado.", 422)
        return data

    def put(self, run_id: UUID, file_id: UUID, content: bytes) -> None:
        path = self._path(run_id, file_id)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".upload-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # O destino só aparece após o conteúdo completo. Reenvios não o alteram.
                os.link(temporary, path)
            except FileExistsError:
                if (
                    hashlib.sha256(self.read(run_id, file_id)).digest()
                    != hashlib.sha256(content).digest()
                ):
                    fail(
                        "FILE_CONTENT_IMMUTABLE",
                        "Arquivo já recebido com conteúdo diferente.",
                    )
        finally:
            os.unlink(temporary)


def inspect_product_image(content: bytes, settings: Settings) -> tuple[str, int, int]:
    """Validação de imagem sintética, NÃO scanner de malware do piloto."""
    if not content or len(content) > settings.product_image_max_bytes:
        fail("FILE_SIZE_INVALID", "Tamanho de imagem inválido.", 422)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content), formats=["PNG", "JPEG"]) as image:
                width, height, fmt = image.width, image.height, image.format
                if (
                    width * height > settings.product_image_max_pixels
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError("Imagem animada ou excede limite")
                image.verify()
            with Image.open(io.BytesIO(content), formats=["PNG", "JPEG"]) as image:
                image.load()
        return "image/png" if fmt == "PNG" else "image/jpeg", width, height
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        fail(
            "FILE_IMAGE_INVALID",
            "Envie PNG/JPEG estático e íntegro dentro dos limites.",
            422,
        )
