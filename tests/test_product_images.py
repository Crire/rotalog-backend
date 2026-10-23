"""HTTP de imagens canônicas: quarentena, worker, galeria e proxy privado."""

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from PIL import Image
from sqlalchemy import func, select
from test_catalog_ordering import PRODUCT, login, ok, setup_supply

from rotalog.catalog.models import ProductImage
from rotalog.core.database import transactional_session
from rotalog.operations.file_models import FileDownloadGrant, FileEvent, StoredFile
from rotalog.operations.file_service import process_product_image_files
from rotalog.operations.file_storage import PrivateImageStorage


def _headers(auth, key=None):
    return auth | {"Idempotency-Key": key or uuid4().hex}


def _png(color="blue"):
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(stream, format="PNG")
    return stream.getvalue()


def _product(client, admin, *, publish=False):
    product = ok(
        client.post(
            "/api/v1/admin/products",
            headers=admin,
            json=PRODUCT | {"name": "Arroz — pacote sintético lacrado"},
        ),
        201,
    )
    if publish:
        product = ok(
            client.post(
                f"/api/v1/admin/products/{product['id']}/publish",
                headers=admin,
                json={"expected_version": product["version"]},
            )
        )
    return product


def _intent(client, admin, product, content=None, **overrides):
    content = content if content is not None else _png()
    body = {
        "purpose": "PRODUCT_IMAGE",
        "product_id": product["id"],
        "size_bytes": len(content),
        "mime_type": "image/png",
        "sha256": hashlib.sha256(content).hexdigest(),
    } | overrides
    return ok(
        client.post("/api/v1/files/upload-intents", headers=_headers(admin), json=body),
        201,
    )


def _received(client, admin, product, content=None, **overrides):
    content = content if content is not None else _png()
    item = _intent(client, admin, product, content, **overrides)
    ok(client.put(item["upload_url"], headers=_headers(admin), content=content), 204)
    return item


def _available(client, admin, product, color="blue"):
    item = _received(client, admin, product, _png(color))
    status = ok(
        client.post(
            f"/api/v1/files/{item['file_id']}/confirm-upload", headers=_headers(admin)
        ),
        202,
    )
    assert status["status"] == "QUARANTINED"
    assert (
        process_product_image_files(
            client.app.state.session_factory, client.app.state.settings
        )
        == 1
    )
    assert (
        ok(client.get(f"/api/v1/files/{item['file_id']}", headers=admin))["status"]
        == "AVAILABLE"
    )
    return item


def _attach(client, admin, product, item, *, key=None):
    gallery = ok(client.get(f"/api/v1/products/{product['id']}/images", headers=admin))
    return client.post(
        f"/api/v1/admin/products/{product['id']}/images",
        headers=_headers(admin, key),
        json={
            "file_id": item["file_id"],
            "expected_version": gallery["product_version"],
            "alt_text": "Embalagem sintética",
        },
    )


def test_upload_quota_replay_and_preserving_downgrade(demo_client, alembic_config):
    admin, _ = login(demo_client)
    product = _product(demo_client, admin)
    body = {
        "purpose": "PRODUCT_IMAGE",
        "product_id": product["id"],
        "size_bytes": len(_png()),
        "mime_type": "image/png",
        "sha256": hashlib.sha256(_png()).hexdigest(),
    }
    first_headers = _headers(admin)
    first = ok(
        demo_client.post(
            "/api/v1/files/upload-intents", headers=first_headers, json=body
        ),
        201,
    )
    for _ in range(19):
        _intent(demo_client, admin, product)
    response = demo_client.post(
        "/api/v1/files/upload-intents", headers=_headers(admin), json=body
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "UPLOAD_INTENT_LIMIT"
    assert (
        ok(
            demo_client.post(
                "/api/v1/files/upload-intents", headers=first_headers, json=body
            ),
            201,
        )
        == first
    )
    # Mesmo sem pendências, o limite de criação por minuto permanece ativo.
    with transactional_session(demo_client.app.state.session_factory) as session:
        for item in session.scalars(select(StoredFile)):
            item.status = "REJECTED"
    response = demo_client.post(
        "/api/v1/files/upload-intents", headers=_headers(admin), json=body
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "UPLOAD_RATE_LIMIT"
    with pytest.raises(RuntimeError, match="Downgrade V5 bloqueado"):
        command.downgrade(alembic_config, "20261023_0007")


def test_image_cycle_catalog_offer_and_authenticated_download(demo_client):
    supplier, _, product, _, offer, _, _ = setup_supply(demo_client)
    admin, _ = login(demo_client)
    buyer, _ = login(demo_client, "comprador")
    content = _png()
    body = {
        "purpose": "PRODUCT_IMAGE",
        "product_id": product["id"],
        "size_bytes": len(content),
        "mime_type": "image/png",
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    headers = _headers(admin, "image-intent-idempotent")
    item = ok(
        demo_client.post("/api/v1/files/upload-intents", headers=headers, json=body),
        201,
    )
    assert (
        ok(
            demo_client.post(
                "/api/v1/files/upload-intents", headers=headers, json=body
            ),
            201,
        )
        == item
    )
    assert item["requires_authentication"] and item["status"] == "PENDING_UPLOAD"
    file_path = f"/api/v1/files/{item['file_id']}"
    assert demo_client.get(file_path, headers=buyer).status_code == 404
    assert (
        demo_client.get(file_path + "/download-access", headers=admin).status_code
        == 409
    )
    upload_headers = _headers(admin, "image-content-idempotent")
    ok(
        demo_client.put(item["upload_url"], headers=upload_headers, content=content),
        204,
    )
    ok(
        demo_client.put(item["upload_url"], headers=upload_headers, content=content),
        204,
    )
    assert (
        demo_client.put(
            item["upload_url"], headers=upload_headers, content=_png("red")
        ).status_code
        == 409
    )
    assert (
        demo_client.put(
            item["upload_url"], headers=_headers(admin), content=_png("red")
        ).status_code
        == 409
    )
    assert _attach(demo_client, admin, product, item).status_code == 409
    confirm_headers = _headers(admin, "image-confirm-idempotent")
    confirmed = ok(
        demo_client.post(file_path + "/confirm-upload", headers=confirm_headers), 202
    )
    assert confirmed["status"] == "QUARANTINED"
    assert _attach(demo_client, admin, product, item).status_code == 409
    assert (
        process_product_image_files(
            demo_client.app.state.session_factory, demo_client.app.state.settings
        )
        == 1
    )
    assert (
        ok(
            demo_client.post(file_path + "/confirm-upload", headers=confirm_headers),
            202,
        )
        == confirmed
    )
    gallery = ok(_attach(demo_client, admin, product, item), 201)
    image = gallery["images"][0]
    assert gallery["primary_image_id"] == image["id"] and image["position"] == 0
    assert image["width"] == 8 and image["height"] == 8 and image["is_primary"]
    detail = ok(demo_client.get(f"/api/v1/products/{product['id']}", headers=buyer))
    assert detail["primary_image"]["id"] == image["id"]
    offers = ok(
        demo_client.get(
            "/api/v1/offers", headers=supplier, params={"product_id": product["id"]}
        )
    )
    assert offers["items"][0]["id"] == offer["id"]
    assert offers["items"][0]["product_image"]["file_id"] == item["file_id"]
    assert demo_client.get(image["content_url"]).status_code == 401
    response = demo_client.get(image["content_url"], headers=buyer)
    assert response.status_code == 200 and response.content == content
    assert (
        response.headers["content-type"] == "image/png"
        and response.headers["cache-control"] == "no-store"
    )
    grant_response = demo_client.get(file_path + "/download-access", headers=buyer)
    grant = ok(grant_response)
    assert grant_response.headers["cache-control"] == "no-store"
    assert "?" not in grant["download_url"]
    assert (
        demo_client.get(
            grant["download_url"], headers=supplier | grant["headers"]
        ).status_code
        == 403
    )
    assert (
        demo_client.get(grant["download_url"], headers=buyer | grant["headers"]).content
        == content
    )
    assert (
        demo_client.get(
            grant["download_url"], headers=buyer | grant["headers"]
        ).status_code
        == 403
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        states = list(
            session.scalars(
                select(FileEvent.kind)
                .where(FileEvent.file_id == UUID(item["file_id"]))
                .order_by(FileEvent.created_at)
            )
        )
    assert states == [
        "PENDING_UPLOAD",
        "QUARANTINED",
        "SCAN_QUEUED",
        "SCANNING",
        "AVAILABLE",
    ]


def test_gallery_order_primary_version_limit_and_soft_removal(demo_client):
    admin, _ = login(demo_client)
    buyer, _ = login(demo_client, "comprador")
    product = _product(demo_client, admin, publish=True)
    items = [
        _available(demo_client, admin, product, color)
        for color in ["red", "green", "blue", "white", "black", "yellow"]
    ]
    for item in items[:5]:
        gallery = ok(_attach(demo_client, admin, product, item), 201)
    assert _attach(demo_client, admin, product, items[5]).status_code == 409
    path = f"/api/v1/admin/products/{product['id']}/images"
    ids = [image["id"] for image in gallery["images"]]
    assert (
        demo_client.post(
            path + "/reorder",
            headers=_headers(admin),
            json={
                "expected_version": gallery["product_version"],
                "image_ids": ids[:-1] + [ids[0]],
            },
        ).status_code
        == 422
    )
    assert (
        demo_client.post(
            path + "/reorder",
            headers=_headers(admin),
            json={"expected_version": 1, "image_ids": ids},
        ).status_code
        == 409
    )
    reordered = ok(
        demo_client.post(
            path + "/reorder",
            headers=_headers(admin),
            json={
                "expected_version": gallery["product_version"],
                "image_ids": ids[::-1],
            },
        )
    )
    assert [image["id"] for image in reordered["images"]] == ids[::-1]
    assert reordered["primary_image_id"] == ids[0]
    primary_key = _headers(admin, "image-primary-repeat")
    primary_body = {"expected_version": reordered["product_version"]}
    primary = ok(
        demo_client.post(
            path + f"/{ids[-1]}/set-primary", headers=primary_key, json=primary_body
        )
    )
    assert (
        ok(
            demo_client.post(
                path + f"/{ids[-1]}/set-primary", headers=primary_key, json=primary_body
            )
        )
        == primary
    )
    grant = ok(
        demo_client.get(
            f"/api/v1/files/{items[4]['file_id']}/download-access", headers=buyer
        )
    )
    removed = ok(
        demo_client.request(
            "DELETE",
            path + f"/{ids[-1]}",
            headers=_headers(admin),
            json={"expected_version": primary["product_version"]},
        )
    )
    assert (
        len(removed["images"]) == 4
        and sum(i["is_primary"] for i in removed["images"]) == 1
    )
    assert [i["position"] for i in removed["images"]] == [0, 1, 2, 3]
    assert (
        demo_client.get(
            grant["download_url"], headers=buyer | grant["headers"]
        ).status_code
        == 404
    )
    assert (
        ok(demo_client.get(f"/api/v1/files/{items[4]['file_id']}", headers=admin))[
            "status"
        ]
        == "AVAILABLE"
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ProductImage)
                .where(ProductImage.removed_at.is_not(None))
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ProductImage)
                .where(
                    ProductImage.removed_at.is_(None), ProductImage.is_primary.is_(True)
                )
            )
            == 1
        )


@pytest.mark.parametrize("kind", ["hash", "mime", "format", "size"])
def test_invalid_upload_is_rejected_and_not_downloadable(demo_client, kind):
    admin, _ = login(demo_client)
    product = _product(demo_client, admin)
    content = b"<script>not an image</script>" if kind == "format" else _png()
    overrides = (
        {"sha256": "0" * 64}
        if kind == "hash"
        else {"mime_type": "image/jpeg"}
        if kind == "mime"
        else {"size_bytes": len(content) + 1}
        if kind == "size"
        else {}
    )
    item = _received(demo_client, admin, product, content, **overrides)
    path = f"/api/v1/files/{item['file_id']}"
    assert (
        demo_client.post(path + "/confirm-upload", headers=_headers(admin)).status_code
        == 422
    )
    assert ok(demo_client.get(path, headers=admin))["status"] == "REJECTED"
    assert demo_client.get(path + "/download-access", headers=admin).status_code == 409
    assert _attach(demo_client, admin, product, item).status_code == 409
    assert (
        process_product_image_files(
            demo_client.app.state.session_factory, demo_client.app.state.settings
        )
        == 0
    )


def test_admin_only_drafts_product_binding_and_expired_intent(demo_client):
    admin, _ = login(demo_client)
    buyer, _ = login(demo_client, "comprador")
    supplier, _ = login(demo_client, "fornecedor")
    product = _product(demo_client, admin)
    other = _product(demo_client, admin, publish=True)
    assert (
        demo_client.get(
            f"/api/v1/products/{product['id']}/images", headers=buyer
        ).status_code
        == 404
    )
    assert (
        demo_client.get(f"/api/v1/products/{product['id']}", headers=admin).status_code
        == 200
    )
    item = _available(demo_client, admin, product)
    assert (
        demo_client.post(
            f"/api/v1/admin/products/{product['id']}/images",
            headers=_headers(supplier),
            json={"file_id": item["file_id"], "expected_version": product["version"]},
        ).status_code
        == 403
    )
    assert _attach(demo_client, admin, other, item).status_code == 409
    gallery = ok(_attach(demo_client, admin, product, item), 201)
    assert (
        demo_client.get(gallery["images"][0]["content_url"], headers=buyer).status_code
        == 404
    )
    assert (
        demo_client.get(
            f"/api/v1/products/{other['id']}/images/{gallery['images'][0]['id']}/content",
            headers=admin,
        ).status_code
        == 404
    )
    intent = _intent(demo_client, admin, product)
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.get(StoredFile, UUID(intent["file_id"])).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    assert (
        demo_client.put(
            intent["upload_url"], headers=_headers(admin), content=_png()
        ).status_code
        == 409
    )
    assert (
        demo_client.put(
            item["upload_url"], headers=_headers(buyer), content=_png()
        ).status_code
        == 403
    )
    # Publicação não passa a exigir imagem, nem a alteração da galeria altera estoque/preço.
    assert (
        ok(
            demo_client.post(
                f"/api/v1/admin/products/{other['id']}/publish",
                headers=admin,
                json={"expected_version": other["version"]},
            )
        )["images"]
        == []
    )


def test_worker_recovery_concurrency_and_integrity(demo_client):
    admin, _ = login(demo_client)
    product = _product(demo_client, admin)
    items = [
        _received(demo_client, admin, product, _png(color)) for color in ["red", "blue"]
    ]
    for item in items:
        ok(
            demo_client.post(
                f"/api/v1/files/{item['file_id']}/confirm-upload",
                headers=_headers(admin),
            ),
            202,
        )
    factory, settings = (
        demo_client.app.state.session_factory,
        demo_client.app.state.settings,
    )
    with transactional_session(factory) as session:
        first = session.get(StoredFile, UUID(items[0]["file_id"]))
        first.status, first.scan_token = "SCANNING", uuid4()
        first.scan_until = datetime.now(UTC) - timedelta(seconds=1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: process_product_image_files(factory, settings, limit=1),
                range(2),
            )
        )
    assert sum(results) == 2
    for item in items:
        assert (
            ok(demo_client.get(f"/api/v1/files/{item['file_id']}", headers=admin))[
                "status"
            ]
            == "AVAILABLE"
        )
    third = _received(demo_client, admin, product)
    ok(
        demo_client.post(
            f"/api/v1/files/{third['file_id']}/confirm-upload", headers=_headers(admin)
        ),
        202,
    )
    # Simula corrupção no volume após confirmação; o worker verifica novamente.
    path = (
        settings.product_images_root
        / UUID(product["demo_run_id"]).hex
        / UUID(third["file_id"]).hex
    )
    path.write_bytes(b"corrupted synthetic data")
    assert process_product_image_files(factory, settings) == 1
    assert (
        ok(demo_client.get(f"/api/v1/files/{third['file_id']}", headers=admin))[
            "status"
        ]
        == "REJECTED"
    )


def test_expired_download_and_upload_without_overwrite(demo_client):
    admin, _ = login(demo_client)
    buyer, _ = login(demo_client, "comprador")
    product = _product(demo_client, admin, publish=True)
    item = _available(demo_client, admin, product)
    ok(_attach(demo_client, admin, product, item), 201)
    grant = ok(
        demo_client.get(
            f"/api/v1/files/{item['file_id']}/download-access", headers=buyer
        )
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.scalar(select(FileDownloadGrant)).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    assert (
        demo_client.get(
            grant["download_url"], headers=buyer | grant["headers"]
        ).status_code
        == 403
    )
    storage = PrivateImageStorage(demo_client.app.state.settings)
    assert storage.read(UUID(product["demo_run_id"]), UUID(item["file_id"])) == _png()
    assert (
        demo_client.put(
            item["upload_url"], headers=_headers(admin), content=_png("red")
        ).status_code
        == 409
    )
