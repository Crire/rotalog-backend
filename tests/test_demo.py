"""Fluxo real seed → login Swagger → catálogo persistente em PostgreSQL 17."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rotalog.core.database import transactional_session
from rotalog.core.errors import RotaLogError
from rotalog.demo.fixtures import DEMO_RUN_ID, PRODUCTS
from rotalog.demo.models import DemoRun
from rotalog.demo.seed import seed_demo
from rotalog.identity.models import User
from rotalog.identity.security import AUDIENCE, ISSUER
from rotalog.marketplace.models import Offer


def _login(client: TestClient, role: str = "comprador"):
    return client.post(
        "/api/v1/auth/login",
        data={
            "username": f"{role}@demo.rotalog.invalid",
            "password": "synthetic-test-password",
        },
    )


@pytest.mark.parametrize("role", ["comprador", "fornecedor", "motorista"])
def test_swagger_login_and_seed_catalog(demo_client: TestClient, role: str) -> None:
    response = _login(demo_client, role)
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert response.headers["cache-control"] == "no-store"
    assert payload["user"]["role"] == role
    assert "password_hash" not in payload["user"]
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    assert demo_client.get("/api/v1/auth/me", headers=headers).json() == payload["user"]
    catalog = demo_client.get("/api/v1/ofertas", headers=headers)
    assert catalog.status_code == 200
    data = catalog.json()
    assert data["total"] == 4
    assert data["is_synthetic"] is True
    assert "SIMULAÇÃO" in data["label"]
    assert {item["product_name"] for item in data["items"]} == {
        name for _, name, _ in PRODUCTS
    }
    for item in data["items"]:
        assert item["demo_run_id"] == str(DEMO_RUN_ID)
        assert item["is_synthetic"] is True
        assert isinstance(item["unit_price"], str)
        assert item["available_quantity"] == 100
    assert demo_client.get("/api/v1/offers", headers=headers).json() == data
    second_page = demo_client.get(
        "/api/v1/ofertas?page=2&page_size=2",
        headers=headers,
    ).json()
    assert second_page["total"] == 4 and len(second_page["items"]) == 2
    schema = demo_client.get("/openapi.json").json()
    oauth = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert oauth["flows"]["password"]["tokenUrl"] == "api/v1/auth/login"
    assert schema["paths"]["/api/v1/ofertas"]["get"]["security"]


def test_authentication_failures_are_safe_and_rate_limited(
    demo_client: TestClient,
) -> None:
    response = demo_client.get("/api/v1/ofertas")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "request_id" in response.json()["error"]
    for _ in range(5):
        response = demo_client.post(
            "/api/v1/auth/login",
            data={
                "username": "comprador@demo.rotalog.invalid",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401
        assert "wrong-password" not in response.text
    assert _login(demo_client).status_code == 429
    assert _login(demo_client, "motorista").status_code == 200


def test_unknown_user_and_disabled_demo(demo_client: TestClient) -> None:
    response = demo_client.post(
        "/api/v1/auth/login",
        data={
            "username": "inexistente@demo.rotalog.invalid",
            "password": "synthetic-test-password",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email ou senha inválidos."
    settings = demo_client.app.state.settings.model_copy(update={"demo_enabled": False})
    demo_client.app.state.settings = settings
    assert _login(demo_client).status_code == 403
    with pytest.raises(RotaLogError, match="Demonstração não habilitada"):
        seed_demo(
            demo_client.app.state.session_factory, settings, "synthetic-test-password"
        )


def test_invalid_expired_tokens_and_disabled_users(demo_client: TestClient) -> None:
    settings = demo_client.app.state.settings
    token = _login(demo_client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}corrupted"}
    assert demo_client.get("/api/v1/ofertas", headers=headers).status_code == 401
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(uuid4()),
            "demo_run_id": str(DEMO_RUN_ID),
            "jti": str(uuid4()),
            "iat": now - timedelta(hours=1),
            "exp": now - timedelta(minutes=1),
            "iss": ISSUER,
            "aud": AUDIENCE,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    assert (
        demo_client.get(
            "/api/v1/ofertas",
            headers={"Authorization": f"Bearer {expired}"},
        ).status_code
        == 401
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        user = session.scalar(
            select(User).where(User.email == "comprador@demo.rotalog.invalid")
        )
        user.is_active = False
    assert (
        demo_client.get(
            "/api/v1/ofertas",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 401
    )


def test_seed_is_idempotent_and_data_is_isolated(demo_client: TestClient) -> None:
    factory = demo_client.app.state.session_factory
    seed_demo(factory, demo_client.app.state.settings, "another-test-password")
    assert (
        _login(demo_client).status_code == 200
    )  # Não muda a senha de contas existentes.
    with transactional_session(factory) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 3
        assert session.scalar(select(func.count()).select_from(Offer)) == 4
        for user in session.scalars(select(User)):
            assert user.password_hash.startswith("$argon2id$")
        # Outra execução não pode ver o catálogo da primeira.
        other_run = DemoRun(id=uuid4(), name="outra-execucao")
        session.add(other_run)
        session.flush()
        user = session.scalar(
            select(User).where(User.email == "comprador@demo.rotalog.invalid")
        )
        user.demo_run_id = other_run.id
    token = _login(demo_client).json()["access_token"]
    result = demo_client.get(
        "/api/v1/ofertas",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert result["total"] == 0


def test_closed_demo_run_invalidates_access(demo_client: TestClient) -> None:
    token = _login(demo_client).json()["access_token"]
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.get(DemoRun, DEMO_RUN_ID).is_active = False
    assert _login(demo_client).status_code == 401
    assert (
        demo_client.get(
            "/api/v1/ofertas",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 401
    )
