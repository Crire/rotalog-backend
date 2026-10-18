"""Casos de uso do módulo de identidade."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from rotalog.core.config import Settings
from rotalog.core.database import transactional_session
from rotalog.core.errors import RotaLogError
from rotalog.demo.models import DemoRun
from rotalog.demo.service import require_active_run
from rotalog.identity.models import LoginThrottle, Role, User
from rotalog.identity.schemas import RegisterRequest, TokenResponse, UserResponse
from rotalog.identity.security import (
    create_access_token,
    decode_access_token,
    password_hash,
    require_demo,
)
from rotalog.organizations.models import Organization


def register(
    data: RegisterRequest,
    factory: sessionmaker[Session],
    settings: Settings,
) -> UserResponse:
    require_demo(settings)
    hashed_password = password_hash.hash(data.password.get_secret_value())
    with transactional_session(factory) as session:
        run_id = require_active_run(session)
        organization = Organization(name=data.organization_name, demo_run_id=run_id)
        session.add(organization)
        session.flush()
        user = session.scalar(
            insert(User)
            .values(
                email=data.email,
                name=data.name,
                password_hash=hashed_password,
                role=data.role,
                organization_id=organization.id,
                demo_run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User)
        )
        if user is None:
            # A organização criada acima também sofre rollback no conflito.
            raise RotaLogError(
                code="EMAIL_ALREADY_REGISTERED",
                message="Email já cadastrado.",
                status_code=409,
            )
        return UserResponse.model_validate(user)


def require_supplier(user: UserResponse) -> None:
    """Papéis vêm do usuário autenticado no banco, nunca do corpo da requisição."""
    if user.role != Role.SUPPLIER:
        raise RotaLogError(
            code="SUPPLIER_REQUIRED",
            message="Operação exclusiva de fornecedores.",
            status_code=403,
        )


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return password_hash.hash(token_urlsafe(32))


def login(
    email: str,
    password: str,
    factory: sessionmaker[Session],
    settings: Settings,
) -> TokenResponse:
    require_demo(settings)
    if not email or len(email) > 254 or not password or len(password) > 1024:
        raise RotaLogError(
            code="INVALID_CREDENTIALS",
            message="Email ou senha inválidos.",
            status_code=401,
        )
    normalized_email = email.strip().lower()
    identifier = sha256(normalized_email.encode()).hexdigest()
    error = None
    result = None
    with transactional_session(factory) as session:
        session.execute(
            insert(LoginThrottle)
            .values(identifier=identifier, failures=0)
            .on_conflict_do_nothing(index_elements=[LoginThrottle.identifier])
        )
        throttle = session.scalar(
            select(LoginThrottle)
            .where(LoginThrottle.identifier == identifier)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if throttle.blocked_until is not None and throttle.blocked_until > now:
            error = RotaLogError(
                code="LOGIN_RATE_LIMITED",
                message="Aguarde antes de tentar novamente.",
                status_code=429,
            )
        else:
            user = session.scalar(
                select(User)
                .join(DemoRun, DemoRun.id == User.demo_run_id)
                .where(
                    User.email == normalized_email,
                    User.is_active.is_(True),
                    DemoRun.is_active.is_(True),
                )
            )
            valid_password = password_hash.verify(
                password,
                user.password_hash if user else _dummy_hash(),
            )
            if user is None or not valid_password:
                throttle.failures += 1
                if throttle.failures >= 5:
                    delay = min(900, 30 * 2 ** min(throttle.failures - 5, 5))
                    throttle.blocked_until = now + timedelta(seconds=delay)
                error = RotaLogError(
                    code="INVALID_CREDENTIALS",
                    message="Email ou senha inválidos.",
                    status_code=401,
                )
            else:
                throttle.failures = 0
                throttle.blocked_until = None
                result = TokenResponse(
                    access_token=create_access_token(
                        user.id, user.demo_run_id, settings
                    ),
                    user=UserResponse.model_validate(user),
                )
    # Falhas devem ser persistidas antes de devolver o erro HTTP.
    if error is not None:
        raise error
    assert result is not None
    return result


def authenticate(
    token: str,
    factory: sessionmaker[Session],
    settings: Settings,
) -> UserResponse:
    user_id, demo_run_id = decode_access_token(token, settings)
    with transactional_session(factory) as session:
        user = session.scalar(
            select(User)
            .join(DemoRun, DemoRun.id == User.demo_run_id)
            .where(
                User.id == user_id,
                User.demo_run_id == demo_run_id,
                User.is_active.is_(True),
                DemoRun.is_active.is_(True),
            )
        )
        if user is None:
            raise RotaLogError(
                code="INVALID_TOKEN",
                message="Usuário ou execução indisponível.",
                status_code=401,
            )
        return UserResponse.model_validate(user)
