"""Arquivos comerciais privados; distintos das evidências de entrega legadas."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class StoredFile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stored_file"
    __table_args__ = (
        CheckConstraint("purpose = 'PRODUCT_IMAGE'", name="purpose_valid"),
        CheckConstraint(
            "status IN ('PENDING_UPLOAD','QUARANTINED','SCANNING','AVAILABLE','REJECTED','RETENTION_HOLD','DELETION_PENDING','DELETED')",
            name="status_valid",
        ),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 8388608", name="size_valid"),
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("product.id", ondelete="RESTRICT"), index=True
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT")
    )
    purpose: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING_UPLOAD", server_default="PENDING_UPLOAD"
    )
    size_bytes: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64))
    received_size: Mapped[int | None] = mapped_column(Integer)
    received_sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_token: Mapped[UUID | None]
    scan_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scanner: Mapped[str | None] = mapped_column(String(60))
    rejection_reason: Mapped[str | None] = mapped_column(String(60))


class FileEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_event"
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_file.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(40))


class FileDownloadGrant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_download_grant"
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_file.id", ondelete="RESTRICT")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_session.id", ondelete="RESTRICT")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
