"""Storage/contratos sem banco; arquivos criados somente no tmp_path do teste."""

import asyncio
import io
import stat
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError
from starlette.requests import Request

from rotalog.core.config import Settings
from rotalog.core.errors import RotaLogError
from rotalog.operations.file_schemas import UploadIntent
from rotalog.operations.file_storage import PrivateImageStorage, inspect_product_image
from rotalog.operations.file_transport import receive_limited_body


def _settings(tmp_path, **extra):
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/rotalog_test",
        product_images_root=tmp_path / "private-images",
        **extra,
    )


def test_atomic_private_storage_and_no_overwrite(tmp_path):
    settings = _settings(tmp_path)
    storage = PrivateImageStorage(settings)
    run_id, file_id = uuid4(), uuid4()
    storage.put(run_id, file_id, b"synthetic original")
    storage.put(run_id, file_id, b"synthetic original")
    with pytest.raises(RotaLogError, match="conteúdo diferente"):
        storage.put(run_id, file_id, b"synthetic replacement")
    assert storage.read(run_id, file_id) == b"synthetic original"
    path = settings.product_images_root / run_id.hex / file_id.hex
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.product_images_root.stat().st_mode) == 0o700
    assert not list(path.parent.glob(".upload-*"))


def test_static_image_limits_and_mime_detection(tmp_path):
    settings = _settings(tmp_path)
    for fmt, mime in [("PNG", "image/png"), ("JPEG", "image/jpeg")]:
        stream = io.BytesIO()
        Image.new("RGB", (8, 8)).save(stream, format=fmt)
        assert inspect_product_image(stream.getvalue(), settings) == (mime, 8, 8)
        with pytest.raises(RotaLogError):
            inspect_product_image(
                stream.getvalue(), _settings(tmp_path, product_image_max_pixels=4)
            )
    animation = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(
        animation,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (8, 8), "blue")],
        duration=100,
        loop=0,
    )
    with pytest.raises(RotaLogError):
        inspect_product_image(animation.getvalue(), settings)
    for invalid in [b"", b"<svg>not allowed</svg>", b"not an image"]:
        with pytest.raises(RotaLogError):
            inspect_product_image(invalid, settings)


def test_upload_contract_rejects_paths_svg_invalid_size_and_hash():
    base = {
        "purpose": "PRODUCT_IMAGE",
        "product_id": uuid4(),
        "size_bytes": 100,
        "mime_type": "image/png",
        "sha256": "a" * 64,
    }
    for invalid in [
        {"filename": "../../file.png"},
        {"mime_type": "image/svg+xml"},
        {"size_bytes": 8388609},
        {"size_bytes": -1},
        {"sha256": "not a hash"},
        {"purpose": "DELIVERY_PROOF"},
    ]:
        with pytest.raises(ValidationError):
            UploadIntent(**(base | invalid))


def test_binary_transport_limits_even_without_content_length():
    async def receive(chunks, headers=()):
        iterator = iter(chunks)

        async def next_chunk():
            return {"type": "http.request", "body": next(iterator), "more_body": True}

        return await receive_limited_body(
            Request({"type": "http", "headers": list(headers)}, receive=next_chunk), 4
        )

    for chunks, headers, expected_status in [
        ([b"123", b"45"], (), 413),
        ([], ((b"content-length", b"5"),), 413),
        ([], ((b"content-length", b"invalid"),), 422),
        ([], ((b"content-length", b"-1"),), 413),
    ]:
        with pytest.raises(RotaLogError) as error:
            asyncio.run(receive(chunks, headers))
        assert error.value.status_code == expected_status
