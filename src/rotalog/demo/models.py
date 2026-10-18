"""Identificação persistente de cada dataset exclusivamente sintético."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class DemoRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demo_run"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
