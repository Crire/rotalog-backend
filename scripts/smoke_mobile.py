"""Blocos HTTP da demo mobile; sem acesso direto ao banco ou sucesso simulado."""

import hashlib
import time
from datetime import UTC, datetime
from uuid import uuid4


def exercise_cargo(request, route, supplier, driver, suffix):
    prefix = f"/api/v1/routes/{route['id']}"
    view = request("GET", prefix + "/manifest", headers=driver)

    def command(name, view, auth=driver, **extra):
        return request(
            "POST",
            prefix + "/" + name,
            headers=auth | {"Idempotency-Key": f"{name.split('/')[-1]}-{uuid4().hex}"},
            json={
                "expected_version": view["route_version"],
                "manifest_version": view["manifest_version"],
            }
            | extra,
        )

    view = request(
        "POST",
        prefix + "/cargo-inspection",
        headers=driver | {"Idempotency-Key": f"inspection-{suffix}"},
        json={"expected_version": view["route_version"]},
    )
    lines = [i["id"] for i in view["lines"]]
    view = command("cargo-checks", view, declaration=True, checked_line_ids=lines)
    first = view["lines"][0]
    view = request(
        "POST",
        prefix + "/cargo-issues",
        expected=201,
        headers=driver | {"Idempotency-Key": f"issue-{suffix}"},
        json={
            "expected_version": view["route_version"],
            "manifest_version": view["manifest_version"],
            "fulfillment_line_id": first["id"],
            "expected_quantity": first["expected_quantity"],
            "observed_quantity": first["expected_quantity"] - 1,
            "category": "MISSING",
            "reason": "SIMULAÇÃO: falta de uma embalagem durante conferência",
        },
    )
    assert not view["declaration_valid"] and view["unresolved_issues"] == 1
    view = command(
        f"cargo-issues/{view['issues'][0]['id']}/resolve",
        view,
        supplier,
        correction="SIMULAÇÃO: embalagem reposta e carga restaurada ao manifesto aprovado",
    )
    assert not view["declaration_valid"] and view["unresolved_issues"] == 0
    view = command("cargo-checks", view, declaration=True, checked_line_ids=lines)
    receipt = {
        "expected_version": view["route_version"],
        "manifest_version": view["manifest_version"],
        "declaration": True,
    }
    headers = driver | {"Idempotency-Key": f"receipt-{suffix}"}
    received = request(
        "POST", prefix + "/cargo-receipts", headers=headers, json=receipt
    )
    assert (
        request("POST", prefix + "/cargo-receipts", headers=headers, json=receipt)
        == received
    )
    route = request("GET", prefix, headers=driver)
    assert route["state"] == "READY_TO_START" and not route["started_at"]
    return route


def exercise_tracking(request, route, driver, suffix):
    prefix = f"/api/v1/routes/{route['id']}"
    body = {
        "client_batch_id": str(uuid4()),
        "device_id": f"smoke-mobile-{suffix}",
        "points": [
            {
                "sequence_no": 1,
                "captured_at_device": datetime.now(UTC).isoformat(),
                "latitude": "-3.100000",
                "longitude": "-60.000000",
                "accuracy_meters": "10.00",
            }
        ],
    }
    result = request("POST", prefix + "/location-batches", headers=driver, json=body)
    assert (
        request("POST", prefix + "/location-batches", headers=driver, json=body)
        == result
    )
    position = request("GET", prefix + "/tracking/current", headers=driver)
    assert position["state"] == "ACTIVE" and position["position"]["sequence_no"] == 1
    assert request("GET", prefix, headers=driver)["version"] == route["version"]


def upload_evidence(request, attempt_id, kind, content, driver):
    intent = request(
        "POST",
        "/api/v1/files/upload-intents",
        expected=201,
        headers=driver | {"Idempotency-Key": uuid4().hex},
        json={
            "purpose": f"DELIVERY_{kind}",
            "attempt_id": attempt_id,
            "size_bytes": len(content),
            "mime_type": "image/png",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    file_id = intent["file_id"]
    request(
        "PUT",
        intent["upload_url"],
        expected=204,
        headers=driver
        | {"Idempotency-Key": uuid4().hex, "Content-Type": "application/octet-stream"},
        content=content,
    )
    request(
        "POST",
        f"/api/v1/files/{file_id}/confirm-upload",
        expected=202,
        headers=driver | {"Idempotency-Key": uuid4().hex},
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        status = request("GET", f"/api/v1/files/{file_id}", headers=driver)["status"]
        if status == "AVAILABLE":
            return {"id": file_id}
        if status == "REJECTED":
            raise RuntimeError(
                "Arquivo sintético rejeitado; confira o estado seguro pela API"
            )
        time.sleep(0.5)
    raise RuntimeError(
        "Worker não disponibilizou arquivo em 45s; confira o worker e o volume privado compartilhado"
    )
