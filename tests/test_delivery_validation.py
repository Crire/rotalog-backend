"""Validações que rodam mesmo sem PostgreSQL configurado."""

import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from rotalog.core.errors import RotaLogError
from rotalog.logistics.delivery_schemas import Destination, ProofInput
from rotalog.logistics.delivery_service import MAX_EVIDENCE_BYTES, validate_image


def test_private_image_validation():
    for fmt, mime in [("PNG", "image/png"), ("JPEG", "image/jpeg")]:
        image = io.BytesIO()
        Image.new("RGB", (8, 8)).save(image, format=fmt)
        assert validate_image(image.getvalue()) == mime
    for content in [b"", b"not an image", b"0" * (MAX_EVIDENCE_BYTES + 1)]:
        with pytest.raises(RotaLogError):
            validate_image(content)


def test_delivery_requires_timezone_and_unique_lines():
    line_id = uuid4()
    body = {
        "expected_version": 1,
        "captured_at": datetime.now(UTC),
        "latitude": "-3.100000",
        "longitude": "-60.000000",
        "accuracy_meters": "10",
        "visible_condition": "Sem avaria",
        "package_count": 1,
        "lines": [{"fulfillment_line_id": line_id, "buyer_accepted_quantity": 1}],
    }
    assert ProofInput(**body).receiver_code is None
    for invalid in [
        {"captured_at": "2026-10-23T10:00:00"},
        {"package_count": -1},
        {"lines": body["lines"] * 2},
        {"receiver_code": "arbitrary"},
    ]:
        with pytest.raises(ValidationError):
            ProofInput(**(body | invalid))
    with pytest.raises(ValidationError):
        Destination(
            supplier_order_id=uuid4(),
            address="Destino sintético",
            latitude="-3.1",
            longitude="-60",
            starts_at=datetime.now(UTC),
            ends_at=datetime.now(UTC).replace(year=2025),
        )
