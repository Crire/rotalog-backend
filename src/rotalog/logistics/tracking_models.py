"""Telemetria canônica independente da versão operacional; preserva GPS legado."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class LocationBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "location_batch"
    __table_args__ = (UniqueConstraint("route_id", "driver_id", "client_batch_id"),)
    route_id: Mapped[UUID] = mapped_column(ForeignKey("route.id"), index=True)
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("identity_user.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_session.id"))
    client_batch_id: Mapped[UUID]
    device_id: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)


class RouteLocationPoint(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "route_location_point"
    __table_args__ = (
        UniqueConstraint("route_id", "driver_id", "device_id", "sequence_no"),
        CheckConstraint("sequence_no >= 0", name="sequence_non_negative"),
        CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 AND accuracy_meters >= 0",
            name="coordinates_valid",
        ),
        Index("ix_route_location_point_history", "route_id", "sequence_no", "id"),
        Index("ix_route_location_point_position", "position", postgresql_using="gist"),
    )
    route_id: Mapped[UUID] = mapped_column(ForeignKey("route.id"))
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("identity_user.id"))
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("location_batch.id"))
    device_id: Mapped[str] = mapped_column(String(100))
    sequence_no: Mapped[int] = mapped_column(BigInteger)
    captured_at_device: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    accuracy_meters: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    speed_mps: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    bearing_degrees: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    is_mocked_by_os: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    position: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    flags: Mapped[list] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(64))


class CurrentRoutePosition(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "current_route_position"
    route_id: Mapped[UUID] = mapped_column(ForeignKey("route.id"), unique=True)
    point_id: Mapped[UUID | None] = mapped_column(ForeignKey("route_location_point.id"))
    declared_status: Mapped[str | None] = mapped_column(String(30))
