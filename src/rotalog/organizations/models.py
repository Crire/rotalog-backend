"""Organizações sintéticas usadas na apresentação."""

from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class Organization(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200))
    demo_run_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("demo_run.id", ondelete="RESTRICT"),
        index=True,
    )
