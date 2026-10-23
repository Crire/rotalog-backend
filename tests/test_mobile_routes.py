"""HTTP mobile com PostgreSQL: conferência, divergências, GPS e prova privada."""

import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import func, select
from test_catalog_ordering import account, login, ok
from test_delivery import _command, _image, prepared, started

from rotalog.core.database import transactional_session
from rotalog.identity.models import Role, User
from rotalog.logistics.cargo_models import CargoEvent
from rotalog.logistics.delivery_models import CustodyEvent, Route
from rotalog.logistics.tracking_models import LocationBatch, RouteLocationPoint
from rotalog.operations.file_service import process_product_image_files
from rotalog.ordering.models import FulfillmentLine
from rotalog.organizations.models import Membership


def post(client, path, auth, body, *, key=None):
    return client.post(
        "/api/v1" + path,
        headers=auth | {"Idempotency-Key": key or uuid4().hex},
        json=body,
    )


def manifest(client, data, auth=None):
    return ok(
        client.get(
            f"/api/v1/routes/{data['route']['id']}/manifest",
            headers=auth or data["driver"],
        )
    )


def accept(client, data):
    route = data["route"]
    data["route"] = ok(
        _command(
            client,
            f"/routes/{route['id']}/accept",
            data["driver"],
            route["version"],
            "mobile-route-accept",
        )
    )
    return manifest(client, data)


def cargo_body(view, **extra):
    return {
        "expected_version": view["route_version"],
        "manifest_version": view["manifest_version"],
    } | extra


def check(client, data, view):
    return ok(
        post(
            client,
            f"/routes/{view['route_id']}/cargo-checks",
            data["driver"],
            cargo_body(
                view,
                declaration=True,
                checked_line_ids=[i["id"] for i in view["lines"]],
            ),
        )
    )


def second_driver(client):
    with transactional_session(client.app.state.session_factory) as session:
        source = session.scalar(
            select(User).where(User.email == "motorista@demo.rotalog.invalid")
        )
        user = User(
            email="motorista2@demo.rotalog.invalid",
            name="Segundo motorista sintético",
            password_hash=source.password_hash,
            role=Role.DRIVER,
            organization_id=source.organization_id,
            demo_run_id=source.demo_run_id,
        )
        session.add(user)
        session.flush()
        session.add(
            Membership(
                user_id=user.id, organization_id=user.organization_id, role=Role.DRIVER
            )
        )
    return login(client, "motorista2")[0]


def private_file(client, data, purpose, *, attempt_id=None):
    content = _image()
    context = (
        {"attempt_id": attempt_id} if attempt_id else {"route_id": data["route"]["id"]}
    )
    item = ok(
        post(
            client,
            "/files/upload-intents",
            data["driver"],
            {
                "purpose": purpose,
                "size_bytes": len(content),
                "mime_type": "image/png",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            | context,
        ),
        201,
    )
    ok(
        client.put(
            item["upload_url"],
            headers=data["driver"] | {"Idempotency-Key": uuid4().hex},
            content=content,
        ),
        204,
    )
    ok(
        post(client, f"/files/{item['file_id']}/confirm-upload", data["driver"], None),
        202,
    )
    return item


def test_manifest_checks_issues_and_receipt_preserve_physical_quantities(
    demo_client, alembic_config
):
    data = prepared(demo_client)
    assert manifest(demo_client, data)["read_only"]
    assert (
        post(
            demo_client,
            f"/routes/{data['route']['id']}/cargo-inspection",
            data["driver"],
            {"expected_version": data["route"]["version"]},
        ).status_code
        == 409
    )
    view = accept(demo_client, data)
    assert not view["read_only"]
    prefix = f"/routes/{view['route_id']}"
    assert view["total_sellable_packages"] == 3
    assert view["lines"][0]["quantity_unit"] == "SELLABLE_PACKAGE"
    assert "unit_price" not in view["lines"][0]
    assert not view["inspection_required"]
    view = ok(
        post(
            demo_client,
            prefix + "/cargo-inspection",
            data["driver"],
            {"expected_version": view["route_version"]},
        )
    )
    assert view["inspection_required"] and not view["declaration_valid"]
    assert (
        post(
            demo_client,
            prefix + "/pickup",
            data["driver"],
            {"expected_version": view["route_version"]},
        ).status_code
        == 409
    )
    assert (
        post(
            demo_client,
            prefix + "/cargo-receipts",
            data["driver"],
            cargo_body(view, declaration=True),
        ).status_code
        == 409
    )
    view = check(demo_client, data, view)
    assert view["declaration_valid"]
    before = view
    report = cargo_body(
        view,
        fulfillment_line_id=view["lines"][0]["id"],
        expected_quantity=3,
        observed_quantity=2,
        category="MISSING",
        reason="Uma embalagem não foi encontrada na conferência",
    )
    view = ok(
        post(
            demo_client,
            prefix + "/cargo-issues",
            data["driver"],
            report,
            key="report-cargo-idempotent",
        ),
        201,
    )
    assert not view["declaration_valid"] and view["unresolved_issues"] == 1
    assert (
        ok(
            post(
                demo_client,
                prefix + "/cargo-issues",
                data["driver"],
                report,
                key="report-cargo-idempotent",
            ),
            201,
        )
        == view
    )
    assert (
        post(
            demo_client,
            prefix + "/cargo-checks",
            data["driver"],
            cargo_body(
                view,
                declaration=True,
                checked_line_ids=[i["id"] for i in view["lines"]],
            ),
        ).status_code
        == 409
    )
    issue = view["issues"][0]
    resolve = prefix + f"/cargo-issues/{issue['id']}/resolve"
    resolution = cargo_body(
        view,
        correction="Fornecedor repôs a embalagem faltante, restaurando a carga aprovada",
    )
    assert post(demo_client, resolve, data["driver"], resolution).status_code == 403
    assert post(demo_client, resolve, data["planner"], resolution).status_code == 403
    stranger, _ = account(demo_client, "outro-fornecedor-mobile", "SUPPLIER_OPERATOR")
    assert post(demo_client, resolve, stranger, resolution).status_code == 404
    view = ok(post(demo_client, resolve, data["supplier"], resolution))
    assert view["unresolved_issues"] == 0 and not view["declaration_valid"]
    assert view["manifest_version"] == before["manifest_version"] + 2
    assert (
        post(
            demo_client,
            prefix + "/cargo-receipts",
            data["driver"],
            cargo_body(view, declaration=True),
        ).status_code
        == 409
    )
    assert (
        post(
            demo_client,
            prefix + "/cargo-checks",
            data["driver"],
            cargo_body(view, declaration=True, checked_line_ids=[str(uuid4())]),
        ).status_code
        == 422
    )
    view = check(demo_client, data, view)
    body = cargo_body(view, declaration=True)
    received = ok(
        post(
            demo_client,
            prefix + "/cargo-receipts",
            data["driver"],
            body,
            key="receipt-mobile-idempotent",
        )
    )
    assert received["received_at"] and received["read_only"]
    assert (
        ok(
            post(
                demo_client,
                prefix + "/cargo-receipts",
                data["driver"],
                body,
                key="receipt-mobile-idempotent",
            )
        )
        == received
    )
    route = ok(demo_client.get("/api/v1" + prefix, headers=data["driver"]))
    assert route["state"] == "READY_TO_START" and not route["started_at"]
    assert route["stops"][0]["state"] == "COMPLETED"
    assert route["stops"][1]["state"] == "PENDING"
    assert (
        post(
            demo_client,
            prefix + "/cargo-issues",
            data["driver"],
            report | {"expected_version": route["version"]},
        ).status_code
        == 409
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert (
            session.scalar(
                select(func.sum(CustodyEvent.quantity)).where(
                    CustodyEvent.kind == "WAREHOUSE_TO_DRIVER"
                )
            )
            == 3
        )
        events = list(
            session.scalars(select(CargoEvent).order_by(CargoEvent.created_at))
        )
        assert [e.action for e in events] == [
            "BEGIN",
            "CHECK",
            "REPORT",
            "RESOLVE",
            "CHECK",
            "RECEIPT",
        ]
        assert events[3].role == Role.SUPPLIER and all(
            e.request_id and e.reason for e in events
        )
    with pytest.raises(RuntimeError, match="Downgrade V5 bloqueado"):
        command.downgrade(alembic_config, "20261023_0008")


def test_mobile_authorization_read_only_and_optional_private_photo(demo_client):
    data = prepared(demo_client)
    view = accept(demo_client, data)
    route_id = view["route_id"]
    prefix = f"/routes/{route_id}"
    other = second_driver(demo_client)
    assert (
        demo_client.get("/api/v1" + prefix + "/manifest", headers=other).status_code
        == 404
    )
    assert (
        demo_client.get(
            "/api/v1" + prefix + "/manifest", headers=data["buyer"]
        ).status_code
        == 403
    )
    assert demo_client.get("/api/v1" + prefix, headers=other).status_code == 404
    assert ok(demo_client.get("/api/v1/routes", headers=other))["items"] == []
    assert (
        "cargo:check"
        in ok(demo_client.get("/api/v1/me", headers=data["driver"]))["capabilities"]
    )
    photo = private_file(demo_client, data, "CARGO_ISSUE_PHOTO")
    body = cargo_body(
        view,
        fulfillment_line_id=view["lines"][0]["id"],
        expected_quantity=3,
        observed_quantity=3,
        category="DAMAGED",
        reason="Embalagem com avaria visível no cenário sintético",
        photo_ids=[photo["file_id"]],
    )
    assert (
        post(demo_client, prefix + "/cargo-issues", data["driver"], body).status_code
        == 409
    )
    assert (
        process_product_image_files(
            demo_client.app.state.session_factory, demo_client.app.state.settings
        )
        == 1
    )
    view = ok(post(demo_client, prefix + "/cargo-issues", data["driver"], body), 201)
    assert view["issues"][0]["photo_ids"] == [photo["file_id"]]
    assert (
        demo_client.get(
            f"/api/v1/files/{photo['file_id']}", headers=data["supplier"]
        ).status_code
        == 200
    )
    assert (
        demo_client.get(f"/api/v1/files/{photo['file_id']}", headers=other).status_code
        == 404
    )
    assert (
        post(
            demo_client,
            prefix + "/cargo-issues",
            data["driver"],
            body | cargo_body(view),
        ).status_code
        == 409
    )
    assert (
        ok(demo_client.get("/api/v1" + prefix, headers=data["driver"]))["version"]
        == view["route_version"]
    )


def test_changed_approved_cargo_requires_replanning_and_cannot_be_silently_received(
    demo_client,
):
    data = prepared(demo_client)
    view = accept(demo_client, data)
    view = check(demo_client, data, view)
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.get(
            FulfillmentLine, UUID(view["lines"][0]["id"])
        ).separated_quantity = 2
    latest = manifest(demo_client, data)
    assert latest["requires_replanning"] and not latest["declaration_valid"]
    prefix = f"/routes/{view['route_id']}"
    response = post(
        demo_client,
        prefix + "/cargo-receipts",
        data["driver"],
        cargo_body(latest, declaration=True),
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "CARGO_REPLAN_REQUIRED"
    )
    assert (
        post(
            demo_client,
            prefix + "/pickup",
            data["driver"],
            {"expected_version": latest["route_version"]},
        ).status_code
        == 409
    )


def test_concurrent_receipts_do_not_duplicate_stock_or_custody(demo_client):
    data = prepared(demo_client)
    view = check(demo_client, data, accept(demo_client, data))
    body = cargo_body(view, declaration=True)
    path = f"/routes/{view['route_id']}/cargo-receipts"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: post(
                    demo_client, path, data["driver"], body, key="same-receipt-retry"
                ),
                range(2),
            )
        )
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert (
            session.scalar(
                select(func.sum(CustodyEvent.quantity)).where(
                    CustodyEvent.kind == "WAREHOUSE_TO_DRIVER"
                )
            )
            == 3
        )


def test_worker_standalone_registers_all_models_and_processes_delivery_file(
    demo_client,
):
    data = started(demo_client, prepared(demo_client))
    item = private_file(
        demo_client, data, "DELIVERY_PHOTO", attempt_id=data["attempt"]["id"]
    )
    settings = demo_client.app.state.settings
    env = os.environ.copy()
    env.update(
        ROTALOG_DATABASE_URL=settings.database_url.get_secret_value(),
        ROTALOG_ENVIRONMENT="test",
        ROTALOG_DEMO_ENABLED="true",
        ROTALOG_JWT_SECRET=settings.jwt_secret.get_secret_value(),
        ROTALOG_PRODUCT_IMAGES_ROOT=str(settings.product_images_root),
        ROTALOG_COOKIE_SECURE="false",
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
    )
    result = subprocess.run(
        [sys.executable, "-m", "rotalog.demo.worker", "--once"],
        env=env,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    status = ok(
        demo_client.get(f"/api/v1/files/{item['file_id']}", headers=data["driver"])
    )
    assert status["status"] == "AVAILABLE"


def test_mobile_delivery_with_queued_evidence_and_historical_route(demo_client):
    data = prepared(demo_client)
    view = accept(demo_client, data)
    prefix = f"/routes/{view['route_id']}"
    view = check(demo_client, data, view)
    view = ok(
        post(
            demo_client,
            prefix + "/cargo-receipts",
            data["driver"],
            cargo_body(view, declaration=True),
        )
    )
    route = ok(
        post(
            demo_client,
            prefix + "/start",
            data["driver"],
            {"expected_version": view["route_version"]},
        )
    )
    stop = next(i for i in route["stops"] if i["kind"] == "DELIVERY")
    assert stop["items"][0]["fulfillment_line_id"] == view["lines"][0]["id"]
    attempt = ok(
        post(
            demo_client,
            f"/route-stops/{stop['id']}/delivery-attempts",
            data["driver"],
            {
                "expected_version": route["version"],
                "device_id": "mobile-real-http-test",
            },
        ),
        201,
    )
    data["attempt"] = attempt
    ids = {
        kind: private_file(
            demo_client, data, "DELIVERY_" + kind, attempt_id=attempt["id"]
        )["file_id"]
        for kind in ["PHOTO", "SIGNATURE"]
    }
    auth = ok(
        post(
            demo_client,
            f"/delivery-attempts/{attempt['id']}/receiver-authorizations",
            data["buyer"],
            {"receiver_role": "Responsável pelo recebimento sintético"},
        )
    )
    body = {
        "expected_version": attempt["version"],
        "captured_at": datetime.now(UTC).isoformat(),
        "latitude": "-3.100000",
        "longitude": "-60.000000",
        "accuracy_meters": "10.00",
        "receiver_code": auth["receiver_code"],
        "signature_id": ids["SIGNATURE"],
        "photo_ids": [ids["PHOTO"]],
        "visible_condition": "Embalagens sintéticas lacradas",
        "package_count": 3,
        "lines": [
            {
                "fulfillment_line_id": view["lines"][0]["id"],
                "buyer_accepted_quantity": 3,
            }
        ],
    }
    path = f"/delivery-attempts/{attempt['id']}/complete"
    assert post(demo_client, path, data["driver"], body).status_code == 404
    assert (
        demo_client.get(
            f"/api/v1/files/{ids['PHOTO']}", headers=data["buyer"]
        ).status_code
        == 404
    )
    assert (
        process_product_image_files(
            demo_client.app.state.session_factory, demo_client.app.state.settings
        )
        == 2
    )
    completed = ok(
        post(demo_client, path, data["driver"], body, key="mobile-proof-idempotent")
    )
    assert completed["validation_state"] == "VALID"
    assert (
        ok(post(demo_client, path, data["driver"], body, key="mobile-proof-idempotent"))
        == completed
    )
    assert (
        demo_client.get(
            f"/api/v1/delivery-evidence/{ids['PHOTO']}", headers=data["buyer"]
        ).content
        == _image()
    )
    assert (
        demo_client.get(
            "/api/v1" + prefix + "/tracking/current", headers=data["buyer"]
        ).status_code
        == 404
    )
    route = ok(demo_client.get("/api/v1" + prefix, headers=data["driver"]))
    route = ok(
        post(
            demo_client,
            prefix + "/end-execution",
            data["driver"],
            {"expected_version": route["version"]},
        )
    )
    route = ok(
        post(
            demo_client,
            prefix + "/complete-operation",
            data["driver"],
            {"expected_version": route["version"]},
        )
    )
    assert route["state"] == "OPERATIONALLY_COMPLETED"
    assert (
        ok(
            demo_client.get(
                "/api/v1/routes", headers=data["driver"], params={"active": False}
            )
        )["items"][0]["id"]
        == route["id"]
    )
    assert (
        ok(
            demo_client.get(
                "/api/v1/routes", headers=data["driver"], params={"active": True}
            )
        )["items"]
        == []
    )
    assert manifest(demo_client, data)["read_only"]


def active_route(client):
    data = prepared(client)
    route = data["route"]
    for cmd in ["accept", "pickup", "start"]:
        route = ok(
            post(
                client,
                f"/routes/{route['id']}/{cmd}",
                data["driver"],
                {"expected_version": route["version"]},
            )
        )
    data["route"] = route
    with transactional_session(client.app.state.session_factory) as session:
        session.get(Route, UUID(route["id"])).started_at = datetime.now(
            UTC
        ) - timedelta(minutes=10)
    return data


def point(seq, *, seconds_ago=30, **extra):
    return {
        "sequence_no": seq,
        "captured_at_device": (
            datetime.now(UTC) - timedelta(seconds=seconds_ago)
        ).isoformat(),
        "latitude": "-3.100000",
        "longitude": "-60.000000",
        "accuracy_meters": "10.00",
    } | extra


def batch(points, **extra):
    return {
        "client_batch_id": str(uuid4()),
        "device_id": "mobile-device-01",
        "points": points,
    } | extra


def test_canonical_tracking_duplicates_out_of_order_flags_and_no_version_conflict(
    demo_client,
):
    data = active_route(demo_client)
    route = data["route"]
    prefix = f"/routes/{route['id']}"
    body = batch([point(10)])
    first = ok(post(demo_client, prefix + "/location-batches", data["driver"], body))
    assert first == ok(
        post(demo_client, prefix + "/location-batches", data["driver"], body)
    )
    assert (
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            body | {"device_id": "other-device"},
        ).status_code
        == 409
    )
    older = body | {"client_batch_id": str(uuid4())}
    assert (
        ok(post(demo_client, prefix + "/location-batches", data["driver"], older))[
            "results"
        ][0]["result"]
        == "DUPLICATE"
    )
    tampered = body | {
        "client_batch_id": str(uuid4()),
        "points": [body["points"][0] | {"latitude": "-3.200000"}],
    }
    assert (
        post(
            demo_client, prefix + "/location-batches", data["driver"], tampered
        ).status_code
        == 409
    )
    ok(
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            batch([point(5, seconds_ago=40)]),
        )
    )
    flagged = ok(
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            batch(
                [
                    point(20, seconds_ago=20, is_mocked_by_os=True),
                    point(30, seconds_ago=15, accuracy_meters="1000.00"),
                ]
            ),
        )
    )
    assert flagged["results"][0]["flags"] == ["MOCKED_BY_OS"]
    assert "LOW_ACCURACY" in flagged["results"][1]["flags"]
    current = ok(
        demo_client.get(
            "/api/v1" + prefix + "/tracking/current", headers=data["driver"]
        )
    )
    assert current["position"]["sequence_no"] == 10 and current["state"] == "ACTIVE"
    assert current["operational_version"] == route["version"]
    assert (
        ok(demo_client.get("/api/v1" + prefix, headers=data["driver"]))["version"]
        == route["version"]
    )
    assert (
        demo_client.get(
            "/api/v1" + prefix + "/tracking/current", headers=data["buyer"]
        ).status_code
        == 200
    )
    assert (
        demo_client.get(
            "/api/v1" + prefix + "/tracking/history", headers=data["buyer"]
        ).status_code
        == 403
    )
    history = ok(
        demo_client.get(
            "/api/v1" + prefix + "/tracking/history",
            headers=data["driver"],
            params={"page_size": 2},
        )
    )
    assert [p["sequence_no"] for p in history["items"]] == [5, 10]
    more = ok(
        demo_client.get(
            "/api/v1" + prefix + "/tracking/history",
            headers=data["driver"],
            params={"cursor": history["next_cursor"]},
        )
    )
    assert [p["sequence_no"] for p in more["items"]] == [20, 30]
    assert (
        demo_client.get(
            "/api/v1" + prefix + "/tracking/history",
            headers=data["driver"],
            params={"cursor": "not-a-cursor"},
        ).status_code
        == 422
    )
    ended = ok(
        post(
            demo_client,
            prefix + "/end-execution",
            data["driver"],
            {"expected_version": route["version"]},
        )
    )
    assert ended["state"] == "EXECUTION_ENDED"
    assert (
        post(
            demo_client,
            prefix + "/complete-operation",
            data["driver"],
            {"expected_version": ended["version"]},
        ).status_code
        == 409
    )
    late = ok(
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            batch([point(15, seconds_ago=25)]),
        )
    )
    assert late["results"][0]["result"] == "STORED"
    after = ok(
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            batch([point(40, seconds_ago=-10)]),
        )
    )
    assert after["results"][0]["result"] == "REJECTED"
    current = ok(
        demo_client.get(
            "/api/v1" + prefix + "/tracking/current", headers=data["driver"]
        )
    )
    assert current["state"] == "ENDED" and current["position"]["sequence_no"] == 15
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(RouteLocationPoint)) == 5
        session.get(Route, UUID(route["id"])).execution_ended_at = datetime.now(
            UTC
        ) - timedelta(days=2)
    assert (
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            batch([point(50)]),
        ).status_code
        == 409
    )


def test_tracking_authorization_concurrency_status_and_rate_limit(demo_client):
    data = active_route(demo_client)
    route = data["route"]
    prefix = f"/routes/{route['id']}"
    other = second_driver(demo_client)
    assert (
        post(
            demo_client, prefix + "/location-batches", other, batch([point(1)])
        ).status_code
        == 404
    )
    assert (
        demo_client.get(
            "/api/v1" + prefix + "/tracking/current", headers=other
        ).status_code
        == 404
    )
    assert (
        post(
            demo_client,
            prefix + "/location-batches",
            data["driver"],
            batch([point(1)], driver_id=str(uuid4())),
        ).status_code
        == 403
    )
    body = batch([point(1)])
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: post(
                    demo_client, prefix + "/location-batches", data["driver"], body
                ),
                range(2),
            )
        )
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(LocationBatch)) == 1
        session.scalar(select(RouteLocationPoint)).captured_at_device = datetime.now(
            UTC
        ) - timedelta(minutes=3)
    assert (
        ok(
            demo_client.get(
                "/api/v1" + prefix + "/tracking/current", headers=data["driver"]
            )
        )["state"]
        == "STALE"
    )
    assert (
        ok(
            post(
                demo_client,
                prefix + "/tracking-status",
                data["driver"],
                {"status": "DEGRADED_PERMISSION"},
            )
        )["state"]
        == "DEGRADED_PERMISSION"
    )
    assert (
        ok(
            post(
                demo_client,
                prefix + "/tracking-status",
                data["driver"],
                {"status": "ACTIVE"},
            )
        )["state"]
        == "STALE"
    )
    demo_client.app.state.settings = demo_client.app.state.settings.model_copy(
        update={"tracking_batches_per_minute": 1}
    )
    assert (
        post(
            demo_client, prefix + "/location-batches", data["driver"], batch([point(2)])
        ).status_code
        == 429
    )
    assert (
        ok(post(demo_client, prefix + "/location-batches", data["driver"], body))
        == results[0].json()
    )
