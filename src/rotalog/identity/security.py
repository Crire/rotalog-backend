"""Hash de senha Argon2id e JWT HMAC de curta duração."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from rotalog.core.config import Settings
from rotalog.core.errors import RotaLogError

password_hash = PasswordHash.recommended()
ACCESS_TOKEN_SECONDS = 15 * 60
ISSUER = "rotalog-api"
AUDIENCE = "rotalog-clients"


def require_demo(settings: Settings) -> str:
    if not settings.demo_enabled or settings.jwt_secret is None:
        raise RotaLogError(
            code="DEMO_DISABLED",
            message="Demonstração não habilitada.",
            status_code=403,
        )
    return settings.jwt_secret.get_secret_value()


def create_access_token(user_id: UUID, demo_run_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "demo_run_id": str(demo_run_id),
            "iat": now,
            "exp": now + timedelta(seconds=ACCESS_TOKEN_SECONDS),
            "iss": ISSUER,
            "aud": AUDIENCE,
            "jti": str(uuid4()),
        },
        require_demo(settings),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> tuple[UUID, UUID]:
    secret = require_demo(settings)
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["sub", "demo_run_id", "iat", "exp", "jti"]},
        )
        return UUID(payload["sub"]), UUID(payload["demo_run_id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise RotaLogError(
            code="INVALID_TOKEN",
            message="Token inválido ou expirado.",
            status_code=401,
        ) from exc
