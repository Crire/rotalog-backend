from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rotalog.logistics.cargo_schemas import CargoCheck, CargoIssueCreate
from rotalog.logistics.tracking_schemas import TrackingBatch, TrackingPoint
from rotalog.operations.file_schemas import UploadIntent


def test_mobile_coordinates_accept_android_precision_and_normalize():
    point = TrackingPoint(
        sequence_no=1,
        captured_at_device=datetime.now(UTC),
        latitude=-3.1234567890123,
        longitude=-60.9876543210123,
        accuracy_meters=10.123456789,
    )
    assert str(point.latitude) == "-3.123457"
    assert str(point.longitude) == "-60.987654"
    assert str(point.accuracy_meters) == "10.12"
    for extra in [
        {"latitude": 91},
        {"sequence_no": -1},
        {"sequence_no": True},
        {"captured_at_device": "2026-10-23T12:00:00"},
        {"accuracy_meters": -1},
    ]:
        with pytest.raises(ValidationError):
            TrackingPoint(**(point.model_dump() | extra))
    with pytest.raises(ValidationError):
        TrackingBatch(
            client_batch_id=uuid4(), device_id="mobile-device", points=[point, point]
        )


def test_operational_upload_intents_require_exactly_one_correct_context():
    base = {
        "purpose": "DELIVERY_PHOTO",
        "attempt_id": uuid4(),
        "size_bytes": 20,
        "mime_type": "image/png",
        "sha256": "a" * 64,
    }
    UploadIntent(**base)
    for changes in [
        {"product_id": uuid4()},
        {"route_id": uuid4()},
        {"attempt_id": None},
        {"purpose": "PRODUCT_IMAGE"},
        {"purpose": "CARGO_ISSUE_PHOTO"},
    ]:
        with pytest.raises(ValidationError):
            UploadIntent(**(base | changes))


def test_cargo_commands_require_real_declaration_full_ids_and_justification():
    base = {
        "expected_version": 1,
        "manifest_version": 1,
        "declaration": True,
        "checked_line_ids": [uuid4()],
    }
    CargoCheck(**base)
    for changes in [
        {"declaration": False},
        {"declaration": 1},
        {"checked_line_ids": []},
        {"checked_line_ids": base["checked_line_ids"] * 2},
        {"manifest_version": 0},
    ]:
        with pytest.raises(ValidationError):
            CargoCheck(**(base | changes))
    issue = {
        "expected_version": 1,
        "manifest_version": 1,
        "fulfillment_line_id": uuid4(),
        "expected_quantity": 3,
        "observed_quantity": 2,
        "category": "MISSING",
        "reason": "Descrição sintética da embalagem faltante",
    }
    CargoIssueCreate(**issue)
    for changes in [
        {"observed_quantity": -1},
        {"reason": "ok"},
        {"category": "IGNORAR"},
        {"photo_ids": [uuid4()] * 2},
    ]:
        with pytest.raises(ValidationError):
            CargoIssueCreate(**(issue | changes))
