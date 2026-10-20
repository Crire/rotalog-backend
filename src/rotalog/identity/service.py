"""Casos de uso de identidade e autorização revalidada em cada transação."""

import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from secrets import compare_digest, token_urlsafe
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from rotalog.core.config import Settings
from rotalog.core.contracts import fail
from rotalog.core.database import transactional_session
from rotalog.demo.service import require_active_run
from rotalog.identity.models import AuthSession, LoginThrottle, RefreshToken, Role, User
from rotalog.identity.schemas import (
    PasswordChange,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from rotalog.identity.security import (
    create_access_token,
    csrf_token,
    decode_access_token,
    password_hash,
    require_demo,
    token_hash,
)
from rotalog.organizations.models import Membership, Organization
from rotalog.organizations.service import create_organization, grant_initial_membership

CAPABILITIES = {
    Role.BUYER: ["catalog:read", "checkout:create", "purchase:read"],
    Role.SUPPLIER: [
        "catalog:read",
        "offer:write",
        "inventory:write",
        "supplier_order:manage",
    ],
    Role.ADMIN: ["catalog:read", "product:write", "warehouse:review"],
    Role.DRIVER: [],
}


def _profile(
    session: Session,
    user: User,
    auth_session: AuthSession | None = None,
    organization_id: UUID | None = None,
) -> UserResponse:
    memberships = session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
            Organization.demo_run_id == user.demo_run_id,
        )
        .order_by(Membership.organization_id)
    ).all()
    selected = next(
        (
            row
            for row in memberships
            if row[0].organization_id == (organization_id or user.organization_id)
        ),
        None,
    )
    if selected is None:
        fail("MEMBERSHIP_REQUIRED", "Organização não autorizada.", 403)
    membership = selected[0]
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role,
        organization_id=membership.organization_id,
        demo_run_id=user.demo_run_id,
        session_id=auth_session.id if auth_session else None,
        auth_version=user.auth_version,
        organizations=[
            {"id": str(org.id), "name": org.name, "role": member.role}
            for member, org in memberships
        ],
        capabilities=CAPABILITIES[Role(membership.role)],
    )


def register(
    data: RegisterRequest, factory: sessionmaker[Session], settings: Settings
) -> UserResponse:
    require_demo(settings)
    hashed = password_hash.hash(data.password.get_secret_value())
    with transactional_session(factory) as session:
        run_id = require_active_run(session)
        organization = create_organization(
            session,
            name=data.organization_name,
            demo_run_id=run_id,
            kind="SUPPLIER" if data.role == Role.SUPPLIER else "BUYER",
        )
        user = session.scalar(
            insert(User)
            .values(
                email=data.email,
                name=data.name,
                password_hash=hashed,
                role=data.role,
                organization_id=organization.id,
                demo_run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User)
        )
        if user is None:
            fail("EMAIL_ALREADY_REGISTERED", "Email já cadastrado.")
        grant_initial_membership(
            session, user_id=user.id, organization_id=organization.id, role=data.role
        )
        return _profile(session, user)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return password_hash.hash(token_urlsafe(32))


def _issue(
    session: Session, user: User, auth_session: AuthSession, settings: Settings
) -> TokenResponse:
    raw = token_urlsafe(48)
    session.add(RefreshToken(session_id=auth_session.id, token_hash=token_hash(raw)))
    return TokenResponse(
        access_token=create_access_token(user, auth_session, settings),
        refresh_token=raw,
        csrf_token=csrf_token(str(auth_session.id), settings)
        if auth_session.client_type == "browser"
        else None,
        user=_profile(session, user, auth_session),
    )


def login(
    email: str,
    password: str,
    factory: sessionmaker[Session],
    settings: Settings,
    client_type: str = "native",
    origin: str | None = None,
) -> TokenResponse:
    require_demo(settings)
    if client_type == "browser" and origin not in settings.cors_origins:
        fail("ORIGIN_NOT_ALLOWED", "Origem não autorizada.", 403)
    if not email or len(email) > 254 or not password or len(password) > 1024:
        fail("INVALID_CREDENTIALS", "Email ou senha inválidos.", 401)
    email = email.strip().lower()
    # Argon2 ocorre fora da transação de escrita e dos locks.
    with transactional_session(factory) as session:
        snapshot = session.execute(
            select(User.id, User.password_hash).where(User.email == email)
        ).first()
    hashed = snapshot.password_hash if snapshot else _dummy_hash()
    valid = password_hash.verify(password, hashed)
    error = None
    result = None
    with transactional_session(factory) as session:
        key = token_hash(email)
        session.execute(
            insert(LoginThrottle)
            .values(identifier=key, failures=0)
            .on_conflict_do_nothing()
        )
        throttle = session.scalar(
            select(LoginThrottle)
            .where(LoginThrottle.identifier == key)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if throttle.blocked_until and throttle.blocked_until > now:
            error = ("LOGIN_RATE_LIMITED", "Aguarde antes de tentar novamente.", 429)
        else:
            user = session.scalar(
                select(User)
                .where(User.email == email, User.is_active.is_(True))
                .with_for_update(read=True)
            )
            if user is None or not valid or user.password_hash != hashed:
                throttle.failures += 1
                if throttle.failures >= 5:
                    throttle.blocked_until = now + timedelta(
                        seconds=min(900, 30 * 2 ** min(throttle.failures - 5, 5))
                    )
                error = ("INVALID_CREDENTIALS", "Email ou senha inválidos.", 401)
            else:
                throttle.failures = 0
                throttle.blocked_until = None
                auth_session = AuthSession(
                    user_id=user.id,
                    expires_at=now + timedelta(days=30),
                    client_type=client_type,
                )
                session.add(auth_session)
                session.flush()
                result = _issue(session, user, auth_session, settings)
    if error:
        fail(*error)
    return result


def authenticate(
    token: str,
    factory: sessionmaker[Session],
    settings: Settings,
    organization_id: UUID | None = None,
) -> UserResponse:
    claims = decode_access_token(token, settings)
    try:
        user_id, session_id, run_id = (
            UUID(claims["sub"]),
            UUID(claims["session_id"]),
            UUID(claims["demo_run_id"]),
        )
    except (ValueError, TypeError, KeyError):
        fail("INVALID_TOKEN", "Token inválido.", 401)
    with transactional_session(factory) as session:
        user = session.get(User, user_id)
        auth_session = session.get(AuthSession, session_id)
        if (
            user is None
            or not user.is_active
            or user.demo_run_id != run_id
            or user.auth_version != claims["auth_version"]
            or auth_session is None
            or auth_session.user_id != user.id
            or auth_session.revoked_at is not None
            or auth_session.expires_at <= datetime.now(UTC)
        ):
            fail("INVALID_SESSION", "Sessão inválida ou revogada.", 401)
        return _profile(session, user, auth_session, organization_id)


def authorize(
    session: Session,
    actor: UserResponse,
    roles: set[Role] | None = None,
    *,
    write: bool = False,
) -> User:
    """Revalida usuário, sessão e vínculo sob locks mantidos até o commit."""
    user = session.scalar(
        select(User).where(User.id == actor.id).with_for_update(read=True)
    )
    auth_session = session.scalar(
        select(AuthSession)
        .where(AuthSession.id == actor.session_id)
        .with_for_update(read=True)
    )
    if (
        not user
        or not user.is_active
        or user.demo_run_id != actor.demo_run_id
        or user.auth_version != actor.auth_version
        or not auth_session
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= datetime.now(UTC)
    ):
        fail("INVALID_SESSION", "Sessão inválida ou revogada.", 401)
    membership = session.scalar(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user.id,
            Membership.organization_id == actor.organization_id,
            Membership.is_active.is_(True),
            Organization.demo_run_id == user.demo_run_id,
        )
        .with_for_update(read=True, of=Membership)
    )
    if (
        not membership
        or membership.role != actor.role
        or (roles and membership.role not in roles)
    ):
        fail(
            "CAPABILITY_REQUIRED", "Permissão insuficiente para esta organização.", 403
        )
    if write:
        require_active_run(session, user.demo_run_id)
    return user


def refresh(
    raw: str,
    factory: sessionmaker[Session],
    settings: Settings,
    *,
    browser: bool = False,
    origin: str | None = None,
    csrf: str | None = None,
    logout: bool = False,
) -> TokenResponse | None:
    require_demo(settings)
    error = None
    result = None
    with transactional_session(factory) as session:
        old = session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw))
        )
        if old is None:
            fail("INVALID_REFRESH", "Refresh token inválido.", 401)
        # Ordem estável usuário -> sessão -> token, compartilhada com comandos protegidos.
        snapshot = session.get(AuthSession, old.session_id)
        user = session.scalar(
            select(User).where(User.id == snapshot.user_id).with_for_update(read=True)
        )
        auth_session = session.scalar(
            select(AuthSession)
            .where(AuthSession.id == old.session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        session.refresh(old)
        if auth_session.client_type == "browser":
            if (
                not browser
                or origin not in settings.cors_origins
                or not compare_digest(
                    csrf or "", csrf_token(str(auth_session.id), settings)
                )
            ):
                fail("CSRF_FAILED", "Origem ou token CSRF inválido.", 403)
        elif browser:
            fail("INVALID_REFRESH", "Canal de autenticação inválido.", 401)
        now = datetime.now(UTC)
        if old.used_at is not None:
            auth_session.revoked_at = now
            logging.getLogger(__name__).warning(
                "Refresh reutilizado; família de sessão revogada"
            )
            error = True
        elif (
            auth_session.revoked_at
            or auth_session.expires_at <= now
            or not user.is_active
        ):
            error = True
        elif logout:
            auth_session.revoked_at = now
        else:
            old.used_at = now
            result = _issue(session, user, auth_session, settings)
    if error:
        fail("INVALID_REFRESH", "Sessão inválida ou refresh reutilizado.", 401)
    return result


def revoke(
    actor: UserResponse,
    factory: sessionmaker[Session],
    *,
    all_sessions: bool = False,
    session_id: UUID | None = None,
) -> None:
    with transactional_session(factory) as session:
        # Escrita de sessão pega lock exclusivo do usuário antes dos locks de autorização.
        session.scalar(select(User).where(User.id == actor.id).with_for_update())
        authorize(session, actor)
        query = update(AuthSession).where(AuthSession.user_id == actor.id)
        if not all_sessions:
            query = query.where(AuthSession.id == (session_id or actor.session_id))
        result = session.execute(query.values(revoked_at=datetime.now(UTC)))
        if not result.rowcount:
            fail("SESSION_NOT_FOUND", "Sessão não encontrada.", 404)


def sessions(actor: UserResponse, factory: sessionmaker[Session]) -> list[dict]:
    with transactional_session(factory) as session:
        authorize(session, actor)
        return [
            {
                "id": item.id,
                "client_type": item.client_type,
                "created_at": item.created_at,
                "expires_at": item.expires_at,
                "revoked_at": item.revoked_at,
                "current": item.id == actor.session_id,
            }
            for item in session.scalars(
                select(AuthSession)
                .where(AuthSession.user_id == actor.id)
                .order_by(AuthSession.created_at)
            )
        ]


def change_password(
    data: PasswordChange, actor: UserResponse, factory: sessionmaker[Session]
) -> None:
    with transactional_session(factory) as session:
        user = session.get(User, actor.id)
        previous_hash = user.password_hash
    if not password_hash.verify(
        data.current_password.get_secret_value(), previous_hash
    ):
        fail("INVALID_CREDENTIALS", "Senha atual inválida.", 401)
    hashed = password_hash.hash(data.new_password.get_secret_value())
    with transactional_session(factory) as session:
        user = session.scalar(select(User).where(User.id == actor.id).with_for_update())
        authorize(session, actor, write=True)
        if user.password_hash != previous_hash:
            fail("VERSION_CONFLICT", "Credenciais alteradas; autentique novamente.")
        user.password_hash = hashed
        user.auth_version += 1
        session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id)
            .values(revoked_at=datetime.now(UTC))
        )
