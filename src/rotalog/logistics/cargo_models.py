"""Conferência pré-coleta; não cria outro agregado de pedido ou estoque."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class CargoInspection(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cargo_inspection"
    __table_args__ = (CheckConstraint("version >= 1", name="version_positive"),)
    route_id: Mapped[UUID] = mapped_column(ForeignKey("route.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    fingerprint: Mapped[str] = mapped_column(String(64))
    checked_version: Mapped[int | None] = mapped_column(Integer)
    checked_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_user.id"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_user.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CargoIssue(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cargo_issue"
    __table_args__ = (
        CheckConstraint(
            "expected_quantity >= 0 AND observed_quantity >= 0", name="quantities_valid"
        ),
        CheckConstraint("state IN ('OPEN','RESOLVED')", name="state_valid"),
    )
    route_id: Mapped[UUID] = mapped_column(ForeignKey("route.id"), index=True)
    fulfillment_line_id: Mapped[UUID] = mapped_column(ForeignKey("fulfillment_line.id"))
    reported_by: Mapped[UUID] = mapped_column(ForeignKey("identity_user.id"))
    expected_quantity: Mapped[int] = mapped_column(Integer)
    observed_quantity: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(
        String(20), default="OPEN", server_default="OPEN"
    )
    correction: Mapped[str | None] = mapped_column(String(500))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_user.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CargoIssuePhoto(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cargo_issue_photo"
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("cargo_issue.id"))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("stored_file.id"), unique=True)


class CargoEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cargo_event"
    route_id: Mapped[UUID] = mapped_column(ForeignKey("route.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_user.id"))
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organization.id"))
    role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict] = mapped_column(JSONB)
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
