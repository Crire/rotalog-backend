"""Cenários solicitados: distribuidora, comprador, compra e gerenciamento do pedido."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from rotalog.core.database import transactional_session
from rotalog.ordering.models import CheckoutSession, Purchase, SupplierOrder
from rotalog.ordering.service import expire_checkouts, expire_orders
from rotalog.organizations.models import Membership, Organization

PASSWORD = "senha-sintetica-de-teste-2026"
PRODUCT = {
    "name": "Pizza — mistura seca lacrada 400 g",
    "brand": "Marca Sintética",
    "category": "ALIMENTO_SECO_INDUSTRIALIZADO",
    "net_content": 400,
    "net_content_unit": "g",
    "packaging_type": "Pacote lacrado",
    "packaging_quantity": 1,
    "gross_weight_grams": 450,
    "volume_cm3": 1000,
    "variant_attributes": {"apresentacao": "mistura seca"},
}


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def login(client, alias="admin", password="synthetic-test-password"):
    response = ok(
        client.post(
            "/api/v1/auth/login",
            data={"username": f"{alias}@demo.rotalog.invalid", "password": password},
        )
    )
    return {"Authorization": f"Bearer {response['access_token']}"}, response["user"]


def account(client, alias, role):
    profile = ok(
        client.post(
            "/api/v1/auth/register",
            json={
                "email": f"{alias}@demo.rotalog.invalid",
                "name": f"{alias} Sintético",
                "organization_name": f"Organização {alias} Sintética",
                "password": PASSWORD,
                "role": role,
            },
        ),
        201,
    )
    auth, user = login(client, alias, PASSWORD)
    assert user["id"] == profile["id"]
    return auth, user


def setup_supply(client, quantity=20):
    admin, _ = login(client)
    product = ok(
        client.post("/api/v1/admin/products", headers=admin, json=PRODUCT), 201
    )
    ok(
        client.post(
            f"/api/v1/admin/products/{product['id']}/publish",
            headers=admin,
            json={"expected_version": product["version"]},
        )
    )
    supplier, profile = account(client, "pizza", "SUPPLIER_OPERATOR")
    warehouse = ok(
        client.post(
            f"/api/v1/suppliers/{profile['organization_id']}/warehouses",
            headers=supplier,
            json={
                "name": "Depósito Pizza Sintético",
                "address": "Rua fictícia 123, Manaus",
                "opening_hours": "Seg–Sex 08:00–18:00",
                "region": "MANAUS",
            },
        ),
        201,
    )
    ok(
        client.post(
            f"/api/v1/warehouses/{warehouse['id']}/geocoding-review",
            headers=admin,
            json={
                "expected_version": warehouse["version"],
                "latitude": "-3.100000",
                "longitude": "-60.000000",
                "reason": "Origem sintética da demo",
            },
        )
    )
    offer = ok(
        client.post(
            f"/api/v1/suppliers/{profile['organization_id']}/offers",
            headers=supplier,
            json={
                "product_id": product["id"],
                "warehouse_id": warehouse["id"],
                "unit_price": "29.90",
                "currency": "BRL",
            },
        ),
        201,
    )
    balance = ok(
        client.post(
            "/api/v1/inventory/manual-adjustments",
            headers=supplier,
            json={
                "offer_id": offer["id"],
                "warehouse_id": warehouse["id"],
                "external_sellable_quantity": quantity,
                "safety_stock_quantity": 0,
                "expected_version": 1,
                "reason": "Saldo inicial sintético",
            },
        )
    )
    now = datetime.now(UTC)
    capacity = ok(
        client.post(
            "/api/v1/demo/capacity-slots",
            headers=supplier,
            json={
                "warehouse_id": warehouse["id"],
                "starts_at": (now + timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(days=1)).isoformat(),
                "total_quantity": 100,
            },
        ),
        201,
    )
    return supplier, profile, product, warehouse, offer, balance, capacity


def checkout(
    client,
    buyer,
    offer,
    capacity,
    quantity=3,
    key="checkout-test-001",
    accepts_partial=False,
):
    return client.post(
        "/api/v1/checkouts",
        headers=buyer | {"Idempotency-Key": key},
        json={
            "items": [{"offer_id": offer["id"], "quantity": quantity}],
            "capacity_slot_id": capacity["id"],
            "accepts_partial": accepts_partial,
        },
    )


def purchase(client, buyer, checkout_data, key="payment-test-001"):
    return client.post(
        f"/api/v1/checkouts/{checkout_data['id']}/confirm-payment",
        headers=buyer | {"Idempotency-Key": key},
        json={"expected_version": checkout_data["version"]},
    )


def test_three_requested_scenarios_and_supplier_preparation(demo_client):
    supplier, profile, product, _warehouse, offer, _balance, capacity = setup_supply(
        demo_client
    )
    buyer, _ = account(demo_client, "comprador-pizza", "BUYER_ADMIN")
    suppliers = ok(demo_client.get("/api/v1/suppliers", headers=buyer))
    assert profile["organization_id"] in {item["id"] for item in suppliers["items"]}
    products = ok(
        demo_client.get("/api/v1/products", headers=buyer, params={"search": "Pizza"})
    )
    assert products["items"][0]["id"] == product["id"]
    offers = ok(
        demo_client.get(
            "/api/v1/offers",
            headers=buyer,
            params={
                "supplier_id": profile["organization_id"],
                "product_id": product["id"],
                "region": "MANAUS",
            },
        )
    )
    assert offers["items"][0]["available_quantity"] == 20
    created = ok(checkout(demo_client, buyer, offer, capacity), 201)
    assert created["total"] == "89.70" and created["currency"] == "BRL"
    assert (
        ok(demo_client.get("/api/v1/supplier-orders", headers=supplier))["total"] == 0
    )
    paid = ok(purchase(demo_client, buyer, created))
    assert paid["provider"] == "SIMULATED" and paid["payment_state"] == "CAPTURED"
    assert ok(purchase(demo_client, buyer, created)) == paid
    purchases = ok(demo_client.get("/api/v1/purchases", headers=buyer))
    assert purchases["total"] == 1
    orders = ok(demo_client.get("/api/v1/supplier-orders", headers=supplier))
    assert orders["total"] == 1
    order = orders["items"][0]
    assert order["state"] == "AWAITING_SUPPLIER_DECISION"
    assert order["items"][0]["requested_quantity"] == 3
    accept_payload = {
        "expected_version": order["version"],
        "lines": [{"order_item_id": order["items"][0]["id"], "accepted_quantity": 3}],
    }
    accepted = ok(
        demo_client.post(
            f"/api/v1/supplier-orders/{order['id']}/acceptance",
            headers=supplier | {"Idempotency-Key": "acceptance-test-001"},
            json=accept_payload,
        )
    )
    assert accepted["state"] == "ACCEPTED"
    assert (
        ok(
            demo_client.post(
                f"/api/v1/supplier-orders/{order['id']}/acceptance",
                headers=supplier | {"Idempotency-Key": "acceptance-test-001"},
                json=accept_payload,
            )
        )
        == accepted
    )
    separating = ok(
        demo_client.post(
            f"/api/v1/supplier-orders/{order['id']}/start-separation",
            headers=supplier,
            json={"expected_version": accepted["version"]},
        )
    )
    fulfillment = ok(
        demo_client.post(
            f"/api/v1/supplier-orders/{order['id']}/fulfillments",
            headers=supplier,
            json={
                "expected_version": separating["version"],
                "lines": [
                    {"order_item_id": order["items"][0]["id"], "allocated_quantity": 3}
                ],
            },
        ),
        201,
    )
    separated = ok(
        demo_client.post(
            f"/api/v1/fulfillments/{fulfillment['id']}/separation-results",
            headers=supplier,
            json={
                "expected_version": fulfillment["version"],
                "lines": [
                    {
                        "fulfillment_line_id": fulfillment["lines"][0]["id"],
                        "separated_quantity": 3,
                    }
                ],
            },
        )
    )
    ready = ok(
        demo_client.post(
            f"/api/v1/fulfillments/{fulfillment['id']}/mark-ready",
            headers=supplier,
            json={"expected_version": separated["version"]},
        )
    )
    assert ready["state"] == "READY_TO_DISPATCH"
    order = ok(demo_client.get(f"/api/v1/supplier-orders/{order['id']}", headers=buyer))
    assert (
        order["state"] == "READY_TO_DISPATCH"
        and order["items"][0]["separated_quantity"] == 3
    )
    current = ok(
        demo_client.get(
            "/api/v1/inventory", headers=supplier, params={"offer_id": offer["id"]}
        )
    )["items"][0]
    assert (
        current["external_sellable_quantity"] == 20
        and current["rotalog_reserved_not_reflected_quantity"] == 3
        and current["effective_sellable_quantity"] == 17
    )
    assert (
        ok(
            demo_client.get(
                f"/api/v1/purchases/{paid['purchase_id']}/payments", headers=buyer
            )
        )[0]["amount"]
        == "89.70"
    )
    assert (
        ok(
            demo_client.get(
                f"/api/v1/supplier-orders/{order['id']}/financial-summary",
                headers=supplier,
            )
        )["protected"]
        == "89.70"
    )


def test_permissions_isolation_and_registration_validation(demo_client):
    supplier, profile, _product, warehouse, offer, balance, capacity = setup_supply(
        demo_client
    )
    other, _ = account(demo_client, "outro", "SUPPLIER_OPERATOR")
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    another_buyer, _ = account(demo_client, "buyer2", "BUYER_ADMIN")
    assert (
        demo_client.post(
            "/api/v1/admin/products", headers=supplier, json=PRODUCT
        ).status_code
        == 403
    )
    assert (
        demo_client.post(
            "/api/v1/admin/products", headers=buyer, json=PRODUCT
        ).status_code
        == 403
    )
    assert ok(demo_client.get("/api/v1/inventory", headers=other))["total"] == 0
    payload = {
        "offer_id": offer["id"],
        "warehouse_id": warehouse["id"],
        "expected_version": balance["version"],
        "external_sellable_quantity": 50,
        "reason": "Tentativa indevida",
    }
    assert (
        demo_client.post(
            "/api/v1/inventory/manual-adjustments", headers=other, json=payload
        ).status_code
        == 404
    )
    created = ok(checkout(demo_client, buyer, offer, capacity), 201)
    assert (
        demo_client.get(
            f"/api/v1/checkouts/{created['id']}", headers=another_buyer
        ).status_code
        == 404
    )
    paid = ok(purchase(demo_client, buyer, created))
    oid = paid["supplier_order_ids"][0]
    for actor in (other, another_buyer):
        assert (
            demo_client.get(f"/api/v1/supplier-orders/{oid}", headers=actor).status_code
            == 404
        )
        assert demo_client.get(
            f"/api/v1/purchases/{paid['purchase_id']}", headers=actor
        ).status_code in (403, 404)
    assert demo_client.get("/api/v1/inventory", headers=buyer).status_code == 403
    assert (
        demo_client.get(
            "/api/v1/offers",
            headers=buyer | {"X-Organization-Id": profile["organization_id"]},
        ).status_code
        == 403
    )
    assert (
        demo_client.post(
            "/api/v1/auth/register",
            json={
                "email": "evil@example.com",
                "password": PASSWORD,
                "name": "Teste",
                "organization_name": "Org",
                "role": "ROTALOG_ADMIN",
            },
        ).status_code
        == 422
    )


def test_duplicate_registration_and_revoked_membership(demo_client):
    supplier, profile = account(demo_client, "duplicado", "SUPPLIER_OPERATOR")
    factory = demo_client.app.state.session_factory
    with transactional_session(factory) as session:
        count = session.scalar(select(func.count()).select_from(Organization))
    response = demo_client.post(
        "/api/v1/auth/register",
        json={
            "email": " DUPLICADO@DEMO.ROTALOG.INVALID ",
            "password": PASSWORD,
            "name": "Teste",
            "organization_name": "Org",
            "role": "SUPPLIER_OPERATOR",
        },
    )
    assert response.status_code == 409
    with transactional_session(factory) as session:
        assert session.scalar(select(func.count()).select_from(Organization)) == count
        session.scalar(
            select(Membership).where(Membership.user_id == profile["id"])
        ).is_active = False
    assert demo_client.get("/api/v1/warehouses", headers=supplier).status_code == 403


def test_stock_versions_reservations_idempotency_and_expiry(demo_client):
    supplier, _, _, warehouse, offer, balance, capacity = setup_supply(
        demo_client, quantity=5
    )
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    first = ok(checkout(demo_client, buyer, offer, capacity, quantity=4), 201)
    assert ok(checkout(demo_client, buyer, offer, capacity, quantity=4), 201) == first
    assert checkout(demo_client, buyer, offer, capacity, quantity=3).status_code == 409
    assert (
        checkout(
            demo_client, buyer, offer, capacity, quantity=2, key="checkout-second-001"
        ).status_code
        == 409
    )
    adjustment = {
        "offer_id": offer["id"],
        "warehouse_id": warehouse["id"],
        "expected_version": balance["version"],
        "external_sellable_quantity": 1,
        "reason": "Ajuste sintético",
    }
    assert (
        demo_client.post(
            "/api/v1/inventory/manual-adjustments", headers=supplier, json=adjustment
        ).status_code
        == 409
    )
    adjustment["expected_version"] += 1
    assert (
        demo_client.post(
            "/api/v1/inventory/manual-adjustments", headers=supplier, json=adjustment
        ).status_code
        == 409
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.get(CheckoutSession, first["id"]).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    assert expire_checkouts(demo_client.app.state.session_factory) == 1
    assert expire_checkouts(demo_client.app.state.session_factory) == 0
    assert purchase(demo_client, buyer, first).status_code == 409
    current = ok(demo_client.get("/api/v1/inventory", headers=supplier))["items"][0]
    assert (
        current["rotalog_reserved_not_reflected_quantity"] == 0
        and current["effective_sellable_quantity"] == 5
    )


def test_concurrent_checkouts_do_not_oversell(demo_client):
    _, _, _, _, offer, _, capacity = setup_supply(demo_client, quantity=5)
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda n: checkout(
                    demo_client,
                    buyer,
                    offer,
                    capacity,
                    quantity=4,
                    key=f"concurrent-checkout-{n}",
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [201, 409]


def test_refusal_releases_stock_and_refunds_simulated_payment(demo_client):
    supplier, _, _, _, offer, _, capacity = setup_supply(demo_client)
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    created = ok(checkout(demo_client, buyer, offer, capacity), 201)
    paid = ok(purchase(demo_client, buyer, created))
    order = ok(
        demo_client.get(
            f"/api/v1/supplier-orders/{paid['supplier_order_ids'][0]}", headers=supplier
        )
    )
    accepted = ok(
        demo_client.post(
            f"/api/v1/supplier-orders/{order['id']}/acceptance",
            headers=supplier | {"Idempotency-Key": "refusal-test-001"},
            json={
                "expected_version": order["version"],
                "lines": [
                    {"order_item_id": order["items"][0]["id"], "accepted_quantity": 0}
                ],
            },
        )
    )
    assert (
        accepted["state"] == "REFUSED"
        and accepted["items"][0]["refunded_quantity"] == 3
    )
    assert (
        ok(
            demo_client.get(
                f"/api/v1/supplier-orders/{order['id']}/financial-summary",
                headers=supplier,
            )
        )["refunded"]
        == "89.70"
    )
    assert (
        ok(demo_client.get("/api/v1/inventory", headers=supplier))["items"][0][
            "effective_sellable_quantity"
        ]
        == 20
    )


@pytest.mark.parametrize(
    "value", [29.9, -1, "-0.01", "0.001", "NaN", "1e999999", "9999999999999.99"]
)
def test_price_rejects_floats_negative_or_invalid_values(demo_client, value):
    supplier, profile, product, warehouse, _, _, _ = setup_supply(demo_client)
    response = demo_client.post(
        f"/api/v1/suppliers/{profile['organization_id']}/offers",
        headers=supplier,
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "unit_price": value,
        },
    )
    assert response.status_code == 422


def test_concurrent_payments_and_price_snapshot(demo_client):
    supplier, _, _, _, offer, _, capacity = setup_supply(demo_client)
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    created = ok(checkout(demo_client, buyer, offer, capacity), 201)
    changed = ok(
        demo_client.post(
            f"/api/v1/offers/{offer['id']}/price-changes",
            headers=supplier,
            json={
                "expected_version": offer["version"],
                "unit_price": "39.90",
                "currency": "BRL",
            },
        )
    )
    assert changed["unit_price"] == "39.90"
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda n: purchase(
                    demo_client, buyer, created, key=f"concurrent-payment-{n}"
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    paid = next(
        response.json() for response in responses if response.status_code == 200
    )
    assert paid["total"] == "89.70"
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(Purchase)) == 1
    order = ok(
        demo_client.get(
            f"/api/v1/supplier-orders/{paid['supplier_order_ids'][0]}", headers=supplier
        )
    )
    assert order["items"][0]["unit_price"] == "29.90"


@pytest.mark.parametrize("action", ["cancel", "expiry"])
def test_cancel_or_acceptance_expiry_refunds_and_releases(demo_client, action):
    supplier, _, _, _, offer, _, capacity = setup_supply(demo_client)
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    created = ok(checkout(demo_client, buyer, offer, capacity), 201)
    paid = ok(purchase(demo_client, buyer, created))
    oid = paid["supplier_order_ids"][0]
    if action == "cancel":
        order = ok(
            demo_client.post(
                f"/api/v1/supplier-orders/{oid}/cancel",
                headers=buyer,
                json={
                    "expected_version": 1,
                    "reason": "Cancelamento sintético solicitado pelo comprador",
                },
            )
        )
        assert order["state"] == "CANCELLED"
    else:
        with transactional_session(demo_client.app.state.session_factory) as session:
            session.get(SupplierOrder, oid).acceptance_deadline = datetime.now(
                UTC
            ) - timedelta(seconds=1)
        assert expire_orders(demo_client.app.state.session_factory) == 1
        assert expire_orders(demo_client.app.state.session_factory) == 0
        order = ok(demo_client.get(f"/api/v1/supplier-orders/{oid}", headers=supplier))
        assert order["state"] == "ACCEPTANCE_EXPIRED"
    assert order["items"][0]["refunded_quantity"] == 3
    assert order["items"][0]["reserved_quantity"] == 0
    assert (
        ok(demo_client.get("/api/v1/inventory", headers=supplier))["items"][0][
            "effective_sellable_quantity"
        ]
        == 20
    )
    assert (
        ok(
            demo_client.get(
                f"/api/v1/supplier-orders/{oid}/financial-summary", headers=supplier
            )
        )["refunded"]
        == "89.70"
    )


def test_expired_payment_releases_before_responding_error(demo_client):
    supplier, _, _, _, offer, _, capacity = setup_supply(demo_client)
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    created = ok(checkout(demo_client, buyer, offer, capacity), 201)
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.get(CheckoutSession, created["id"]).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    assert purchase(demo_client, buyer, created).status_code == 409
    assert (
        ok(demo_client.get("/api/v1/inventory", headers=supplier))["items"][0][
            "effective_sellable_quantity"
        ]
        == 20
    )
    assert ok(demo_client.get("/api/v1/purchases", headers=buyer))["total"] == 0


def test_bad_quantities_versions_and_reason_rejected(demo_client):
    supplier, _, _, warehouse, offer, balance, _ = setup_supply(demo_client)
    payload = {
        "offer_id": offer["id"],
        "warehouse_id": warehouse["id"],
        "expected_version": balance["version"],
        "external_sellable_quantity": 25,
        "reason": "Ajuste sintético",
    }
    for quantity in (-1, True, 1.5, 2_147_483_648):
        assert (
            demo_client.post(
                "/api/v1/inventory/manual-adjustments",
                headers=supplier,
                json=payload | {"external_sellable_quantity": quantity},
            ).status_code
            == 422
        )
    assert (
        demo_client.post(
            "/api/v1/inventory/manual-adjustments",
            headers=supplier,
            json=payload | {"reason": "      "},
        ).status_code
        == 422
    )
    assert (
        demo_client.post(
            "/api/v1/inventory/manual-adjustments",
            headers=supplier,
            json=payload | {"expected_version": 1},
        ).status_code
        == 409
    )
    updated = ok(
        demo_client.post(
            "/api/v1/inventory/manual-adjustments", headers=supplier, json=payload
        )
    )
    assert updated["external_sellable_quantity"] == 25


def test_total_cannot_overflow_bigint(demo_client):
    supplier, _, _, _, offer, _, capacity = setup_supply(demo_client, quantity=100000)
    buyer, _ = account(demo_client, "buyer", "BUYER_ADMIN")
    ok(
        demo_client.post(
            f"/api/v1/offers/{offer['id']}/price-changes",
            headers=supplier,
            json={"expected_version": 1, "unit_price": "999999999999.99"},
        )
    )
    response = checkout(demo_client, buyer, offer, capacity, quantity=100000)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "TOTAL_AMOUNT_OUT_OF_RANGE"
    )
