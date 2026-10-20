"""Idempotência persistente dos comandos comerciais."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class IdempotencyRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (UniqueConstraint("organization_id", "operation", "key"),)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    operation: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
