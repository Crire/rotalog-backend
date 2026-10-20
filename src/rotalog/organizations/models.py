"""Organizações sintéticas usadas na apresentação."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class Organization(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(
        String(20), default="BUYER", server_default="BUYER"
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("demo_run.id", ondelete="RESTRICT"),
        index=True,
    )


class Membership(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "role"),)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
