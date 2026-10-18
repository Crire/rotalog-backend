"""Cadastro, login, criação de Pizza e estoque pelos endpoints reais da demo."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rotalog.api.main import create_app
from rotalog.core.config import Settings
from rotalog.core.database import transactional_session
from rotalog.demo.models import DemoRun
from rotalog.identity.models import User
from rotalog.marketplace.models import InventoryBalance, Offer, Product
from rotalog.organizations.models import Organization

PASSWORD = "senha-sintetica-de-teste-2026"


def registration(
    email: str = "pizza@demo.rotalog.invalid", role: str = "fornecedor"
) -> dict:
    return {
        "email": email,
        "name": "Distribuidor Pizza Sintético",
        "organization_name": "Distribuidora Pizza Sintética",
        "role": role,
        "password": PASSWORD,
    }


def register_and_login(
    client: TestClient, email: str = "pizza@demo.rotalog.invalid"
) -> dict:
    response = client.post("/api/v1/auth/register", json=registration(email))
    assert response.status_code == 201, response.text
    assert "password" not in response.json() and "password_hash" not in response.json()
    response = client.post(
        "/api/v1/auth/login", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_pizza(client: TestClient, headers: dict) -> dict:
    response = client.post(
        "/api/v1/products", json={"name": " Pizza "}, headers=headers
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Pizza"
    response = client.post(
        "/api/v1/ofertas",
        json={
            "product_id": response.json()["id"],
            "unit_price": "29.90",
            "minimum_order_quantity": 1,
            "available_quantity": 20,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_login_pizza_and_inventory(demo_client: TestClient) -> None:
    headers = register_and_login(demo_client)
    offer = create_pizza(demo_client, headers)
    assert offer["is_synthetic"] is True and offer["available_quantity"] == 20
    assert offer["unit_price"] == "29.90"
    path = f"/api/v1/ofertas/{offer['id']}/estoque"
    for quantity in (30, 5, 0, 12):
        response = demo_client.patch(
            path, json={"available_quantity": quantity}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["declared_quantity"] == quantity
        assert response.json()["available_quantity"] == quantity
        assert response.json()["reserved_quantity"] == 0
        assert demo_client.get(path, headers=headers).json() == response.json()
    catalog = demo_client.get("/api/v1/ofertas", headers=headers).json()
    pizza = next(item for item in catalog["items"] if item["id"] == offer["id"])
    assert pizza["available_quantity"] == 12 and pizza["product_name"] == "Pizza"
    assert (
        demo_client.get(
            f"/api/v1/offers/{offer['id']}/inventory", headers=headers
        ).json()["available_quantity"]
        == 12
    )


def test_duplicate_registration_rolls_back_organization(
    demo_client: TestClient,
) -> None:
    register_and_login(demo_client)
    factory = demo_client.app.state.session_factory
    with transactional_session(factory) as session:
        count_before = session.scalar(select(func.count()).select_from(Organization))
        user = session.scalar(
            select(User).where(User.email == "pizza@demo.rotalog.invalid")
        )
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
    payload = registration(" PIZZA@DEMO.ROTALOG.INVALID ")
    response = demo_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    with transactional_session(factory) as session:
        assert (
            session.scalar(select(func.count()).select_from(Organization))
            == count_before
        )


@pytest.mark.parametrize("role", ["comprador", "motorista"])
def test_only_suppliers_can_write(demo_client: TestClient, role: str) -> None:
    response = demo_client.post(
        "/api/v1/auth/login",
        data={
            "username": f"{role}@demo.rotalog.invalid",
            "password": "synthetic-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert (
        demo_client.post(
            "/api/v1/products", json={"name": "Pizza"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        demo_client.post(
            "/api/v1/ofertas",
            json={"product_id": str(uuid4()), "unit_price": "10.00"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        demo_client.patch(
            f"/api/v1/ofertas/{uuid4()}/estoque",
            json={"available_quantity": 10},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        demo_client.get(
            f"/api/v1/ofertas/{uuid4()}/estoque", headers=headers
        ).status_code
        == 403
    )


def test_stock_is_private_to_owning_supplier(demo_client: TestClient) -> None:
    owner = register_and_login(demo_client)
    offer = create_pizza(demo_client, owner)
    another = register_and_login(demo_client, "outro@demo.rotalog.invalid")
    path = f"/api/v1/ofertas/{offer['id']}/estoque"
    assert demo_client.get(path, headers=another).status_code == 404
    assert (
        demo_client.patch(
            path, json={"available_quantity": 500}, headers=another
        ).status_code
        == 404
    )
    assert demo_client.get(path, headers=owner).json()["declared_quantity"] == 20
    assert (
        demo_client.post("/api/v1/products", json={"name": "Pizza"}).status_code == 401
    )


def test_inventory_preserves_reservations_and_rejects_bad_values(
    demo_client: TestClient,
) -> None:
    headers = register_and_login(demo_client)
    offer = create_pizza(demo_client, headers)
    with transactional_session(demo_client.app.state.session_factory) as session:
        balance = session.scalar(
            select(InventoryBalance).where(InventoryBalance.offer_id == offer["id"])
        )
        balance.reserved_quantity = (
            4  # Fixture para o módulo de reservas ainda não implementado.
        )
    path = f"/api/v1/ofertas/{offer['id']}/estoque"
    assert (
        demo_client.patch(
            path, json={"available_quantity": 3}, headers=headers
        ).status_code
        == 409
    )
    for payload in (
        {"available_quantity": -1},
        {"available_quantity": True},
        {"available_quantity": 1.5},
        {"available_quantity": 2_147_483_648},
        {"available_quantity": 10, "reserved_quantity": 0},
    ):
        assert demo_client.patch(path, json=payload, headers=headers).status_code == 422
    response = demo_client.get(path, headers=headers).json()
    assert response["declared_quantity"] == 20 and response["reserved_quantity"] == 4
    assert response["available_quantity"] == 16
    response = demo_client.patch(path, json={"available_quantity": 4}, headers=headers)
    assert response.status_code == 200 and response.json()["available_quantity"] == 0


def test_offer_and_registration_input_validation(demo_client: TestClient) -> None:
    for fields in (
        {"role": "admin"},
        {"role": "motorista"},
        {"password": "curta"},
        {"email": "pessoa@example.com"},
        {"email": "invalido"},
        {"organization_name": " "},
        {"name": " "},
        {"is_active": True},
    ):
        response = demo_client.post(
            "/api/v1/auth/register", json=registration() | fields
        )
        assert response.status_code == 422
        assert PASSWORD not in response.text and "curta" not in response.text
    headers = register_and_login(demo_client)
    product = demo_client.post(
        "/api/v1/products", json={"name": "Pizza"}, headers=headers
    ).json()
    payload = {"product_id": product["id"], "unit_price": "29.90"}
    for fields in (
        {"unit_price": "-0.01"},
        {"unit_price": "0.001"},
        {"unit_price": "NaN"},
        {"unit_price": "1000000000000.00"},
        {"minimum_order_quantity": 0},
        {"available_quantity": -1},
        {"supplier_organization_id": str(uuid4())},
    ):
        assert (
            demo_client.post(
                "/api/v1/ofertas", json=payload | fields, headers=headers
            ).status_code
            == 422
        )
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(Offer)) == 4


def test_product_must_belong_to_same_run(demo_client: TestClient) -> None:
    headers = register_and_login(demo_client)
    with transactional_session(demo_client.app.state.session_factory) as session:
        run = DemoRun(name="outra-demo-pizza")
        session.add(run)
        session.flush()
        product = Product(name="Pizza de outra execução", demo_run_id=run.id)
        session.add(product)
        session.flush()
        product_id = str(product.id)
    assert (
        demo_client.post(
            "/api/v1/ofertas",
            json={"product_id": product_id, "unit_price": "29.90"},
            headers=headers,
        ).status_code
        == 404
    )


def test_registration_requires_demo_and_seed(demo_client: TestClient) -> None:
    demo_client.app.state.settings = demo_client.app.state.settings.model_copy(
        update={"demo_enabled": False}
    )
    assert (
        demo_client.post("/api/v1/auth/register", json=registration()).status_code
        == 403
    )


def test_registration_before_seed(
    alembic_config: Config, demo_settings: Settings
) -> None:
    command.upgrade(alembic_config, "head")
    with TestClient(create_app(demo_settings)) as client:
        response = client.post("/api/v1/auth/register", json=registration())
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DEMO_UNAVAILABLE"
