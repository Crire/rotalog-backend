"""Modelos persistentes do módulo de identidade."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class Role(StrEnum):
    BUYER = "comprador"
    SUPPLIER = "fornecedor"
    DRIVER = "motorista"


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "identity_user"
    __table_args__ = (
        CheckConstraint(
            "role IN ('comprador', 'fornecedor', 'motorista')",
            name="role_valid",
        ),
    )

    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("organization.id", ondelete="RESTRICT"),
        index=True,
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("demo_run.id", ondelete="RESTRICT"),
        index=True,
    )


class LoginThrottle(Base):
    """Bloqueio persistente por identificador, inclusive para emails inexistentes."""

    __tablename__ = "login_throttle"
    __table_args__ = (CheckConstraint("failures >= 0", name="failures_non_negative"),)

    identifier: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
