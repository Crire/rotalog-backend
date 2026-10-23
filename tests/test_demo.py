"""Sessões V5, seed sintético, rotação, revogação e proteção do navegador."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import func, select

from rotalog.core.database import transactional_session
from rotalog.demo.fixtures import DEMO_RUN_ID
from rotalog.demo.models import DemoRun
from rotalog.demo.seed import seed_demo
from rotalog.identity.models import AuthSession, RefreshToken, User
from rotalog.identity.security import AUDIENCE, ISSUER

PASSWORD = "synthetic-test-password"


def login(client, alias="comprador", password=PASSWORD, **kwargs):
    return client.post(
        "/api/v1/auth/login",
        data={"username": f"{alias}@demo.rotalog.invalid", "password": password},
        **kwargs,
    )


def headers(payload):
    return {"Authorization": f"Bearer {payload['access_token']}"}


@pytest.mark.parametrize(
    "alias,role",
    [
        ("comprador", "BUYER_ADMIN"),
        ("fornecedor", "SUPPLIER_OPERATOR"),
        ("motorista", "DRIVER"),
        ("admin", "ROTALOG_ADMIN"),
    ],
)
def test_login_profile_and_canonical_catalog(demo_client, alias, role):
    response = login(demo_client, alias)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["expires_in"] == 600
    assert payload["user"]["role"] == role
    assert response.headers["cache-control"] == "no-store"
    assert (
        demo_client.get("/api/v1/me", headers=headers(payload)).json()
        == payload["user"]
    )
    offers = demo_client.get("/api/v1/offers", headers=headers(payload)).json()
    assert offers["total"] == 4
    assert all(
        isinstance(item["unit_price"], str) and item["currency"] == "BRL"
        for item in offers["items"]
    )
    assert (
        demo_client.get("/api/v1/products", headers=headers(payload)).json()["total"]
        == 4
    )
    claims = jwt.decode(
        payload["access_token"],
        demo_client.app.state.settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=AUDIENCE,
        issuer=ISSUER,
    )
    assert {
        "sub",
        "session_id",
        "auth_version",
        "aud",
        "iat",
        "exp",
        "jti",
    } <= claims.keys()
    assert claims["exp"] - claims["iat"] == 600


def test_rotation_reuse_revokes_entire_session(demo_client):
    initial = login(demo_client).json()
    rotated = demo_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": initial["refresh_token"]}
    )
    assert rotated.status_code == 200
    current = rotated.json()
    assert current["refresh_token"] != initial["refresh_token"]
    assert demo_client.get("/api/v1/me", headers=headers(current)).status_code == 200
    assert (
        demo_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": initial["refresh_token"]}
        ).status_code
        == 401
    )
    assert demo_client.get("/api/v1/me", headers=headers(current)).status_code == 401
    assert (
        demo_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": current["refresh_token"]}
        ).status_code
        == 401
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        assert (
            session.scalar(select(RefreshToken.token_hash)) != initial["refresh_token"]
        )


def test_logout_session_revoke_and_password_change(demo_client):
    first, second = login(demo_client).json(), login(demo_client).json()
    listed = demo_client.get("/api/v1/me/sessions", headers=headers(first)).json()
    other = next(item for item in listed if not item["current"])
    assert (
        demo_client.delete(
            f"/api/v1/me/sessions/{other['id']}", headers=headers(first)
        ).status_code
        == 204
    )
    assert demo_client.get("/api/v1/me", headers=headers(second)).status_code == 401
    assert (
        demo_client.post(
            "/api/v1/auth/password/change",
            headers=headers(first),
            json={
                "current_password": PASSWORD,
                "new_password": "nova-senha-sintetica-2026",
            },
        ).status_code
        == 204
    )
    assert demo_client.get("/api/v1/me", headers=headers(first)).status_code == 401
    assert login(demo_client).status_code == 401
    fresh = login(demo_client, password="nova-senha-sintetica-2026").json()
    assert (
        demo_client.post("/api/v1/auth/logout", headers=headers(fresh)).status_code
        == 204
    )
    assert demo_client.get("/api/v1/me", headers=headers(fresh)).status_code == 401


def test_logout_all_and_inactive_or_expired_sessions(demo_client):
    first, second = login(demo_client).json(), login(demo_client).json()
    assert (
        demo_client.post("/api/v1/auth/logout-all", headers=headers(first)).status_code
        == 204
    )
    for item in (first, second):
        assert demo_client.get("/api/v1/me", headers=headers(item)).status_code == 401
    fresh = login(demo_client).json()
    with transactional_session(demo_client.app.state.session_factory) as session:
        for item in session.scalars(select(AuthSession)):
            item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert demo_client.get("/api/v1/me", headers=headers(fresh)).status_code == 401
    assert (
        demo_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": fresh["refresh_token"]}
        ).status_code
        == 401
    )


def test_invalid_expired_tokens_blocked_user_and_auth_version(demo_client):
    initial = login(demo_client).json()
    assert (
        demo_client.get(
            "/api/v1/me", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    settings = demo_client.app.state.settings
    claims = jwt.decode(
        initial["access_token"],
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=AUDIENCE,
    )
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(
        claims, settings.jwt_secret.get_secret_value(), algorithm="HS256"
    )
    assert (
        demo_client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {expired}"}
        ).status_code
        == 401
    )
    with transactional_session(demo_client.app.state.session_factory) as session:
        user = session.scalar(
            select(User).where(User.email == "comprador@demo.rotalog.invalid")
        )
        user.auth_version += 1
    assert demo_client.get("/api/v1/me", headers=headers(initial)).status_code == 401
    fresh = login(demo_client).json()
    with transactional_session(demo_client.app.state.session_factory) as session:
        session.scalar(
            select(User).where(User.email == "comprador@demo.rotalog.invalid")
        ).is_active = False
    assert demo_client.get("/api/v1/me", headers=headers(fresh)).status_code == 401


def test_seed_is_idempotent_and_closed_run_is_read_only(demo_client):
    factory = demo_client.app.state.session_factory
    seed_demo(factory, demo_client.app.state.settings, "another-synthetic-password")
    payload = login(demo_client).json()
    with transactional_session(factory) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 5
        assert all(
            user.password_hash.startswith("$argon2id$")
            for user in session.scalars(select(User))
        )
        session.get(DemoRun, DEMO_RUN_ID).is_active = False
    assert (
        demo_client.get("/api/v1/offers", headers=headers(payload)).status_code == 200
    )
    assert (
        demo_client.post(
            "/api/v1/auth/register",
            json={
                "email": "novo@demo.rotalog.invalid",
                "name": "Novo",
                "organization_name": "Org",
                "password": PASSWORD,
                "role": "BUYER_ADMIN",
            },
        ).status_code
        == 409
    )


def test_login_rate_limit_and_tenant_context(demo_client):
    for _ in range(5):
        assert login(demo_client, password="wrong").status_code == 401
    assert login(demo_client).status_code == 429
    payload = login(demo_client, "fornecedor").json()
    assert (
        demo_client.get(
            "/api/v1/me", headers=headers(payload) | {"X-Organization-Id": str(uuid4())}
        ).status_code
        == 403
    )
    assert demo_client.get("/api/v1/me").status_code == 401


def test_browser_cookie_csrf_and_cors(demo_client):
    demo_client.app.state.settings = demo_client.app.state.settings.model_copy(
        update={"cors_origins": ["http://localhost:5173"]}
    )
    assert (
        login(
            demo_client,
            params={"client_type": "browser"},
            headers={"Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )
    response = login(
        demo_client,
        params={"client_type": "browser"},
        headers={"Origin": "http://localhost:5173"},
    )
    payload = response.json()
    assert payload["refresh_token"] is None and payload["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert (
        "HttpOnly" in cookie
        and "SameSite=lax" in cookie
        and "Path=/api/v1/auth" in cookie
        and "Domain=" not in cookie
    )
    assert demo_client.post("/api/v1/auth/refresh").status_code == 403
    browser_headers = {
        "Origin": "http://localhost:5173",
        "X-CSRF-Token": payload["csrf_token"],
    }
    assert (
        demo_client.post("/api/v1/auth/refresh", headers=browser_headers).status_code
        == 200
    )
    assert (
        demo_client.post("/api/v1/auth/logout", headers=browser_headers).status_code
        == 204
    )
    assert demo_client.get("/api/v1/me", headers=headers(payload)).status_code == 401


def test_cors_preflight_and_rejected_origins(demo_client):
    response = demo_client.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"
    rejected = demo_client.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": "https://evil.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_explicit_demo_extensions_and_no_v41_mutating_routes(demo_client):
    schema = demo_client.get("/openapi.json").json()
    paths = schema["paths"]
    assert (
        schema["components"]["schemas"]["OfferCreate"]["properties"]["unit_price"][
            "type"
        ]
        == "string"
    )
    assert "/api/v1/auth/me" not in paths and "/api/v1/ofertas" not in paths
    assert "post" not in paths["/api/v1/products"]
    for path in [
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/me",
        "/api/v1/admin/products",
        "/api/v1/inventory/manual-adjustments",
        "/api/v1/checkouts",
        "/api/v1/purchases",
        "/api/v1/supplier-orders",
    ]:
        assert path in paths


def test_concurrent_refresh_reuse_revokes_session(demo_client):
    initial = login(demo_client).json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: demo_client.post(
                    "/api/v1/auth/refresh",
                    json={"refresh_token": initial["refresh_token"]},
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 401]
    issued = next(
        response.json() for response in responses if response.status_code == 200
    )
    assert demo_client.get("/api/v1/me", headers=headers(issued)).status_code == 401
    assert (
        demo_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]}
        ).status_code
        == 401
    )


def test_concurrent_logout_does_not_deadlock(demo_client):
    initial = login(demo_client).json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: demo_client.post(
                    "/api/v1/auth/logout", headers=headers(initial)
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [204, 401]
