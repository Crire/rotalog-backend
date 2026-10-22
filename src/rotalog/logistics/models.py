"""Modelos de rota de entrega e rastreamento do motorista."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class DeliveryRoute(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Rota de uma entrega sintética atribuída a um motorista."""

    __tablename__ = "delivery_route"
    __table_args__ = (
        CheckConstraint(
            "state IN ('ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="state_valid",
        ),
        CheckConstraint(
            "last_latitude IS NULL OR last_latitude BETWEEN -90 AND 90",
            name="last_latitude_valid",
        ),
        CheckConstraint(
            "last_longitude IS NULL OR last_longitude BETWEEN -180 AND 180",
            name="last_longitude_valid",
        ),
        Index(
            "ix_delivery_route_last_position",
            "last_position",
            postgresql_using="gist",
        ),
    )

    supplier_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("supplier_order.id", ondelete="RESTRICT"), unique=True
    )
    driver_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT"), index=True
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT"), index=True
    )
    state: Mapped[str] = mapped_column(
        String(20), default="ASSIGNED", server_default="ASSIGNED"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    last_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    last_position: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    last_accuracy_meters: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverLocationPoint(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Ponto GPS recebido do motorista durante uma rota em andamento."""

    __tablename__ = "driver_location_point"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_valid"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_valid"),
        CheckConstraint("accuracy_meters >= 0", name="accuracy_non_negative"),
        Index("ix_driver_location_point_route_recorded_at", "route_id", "recorded_at"),
        Index(
            "ix_driver_location_point_position",
            "position",
            postgresql_using="gist",
        ),
    )

    route_id: Mapped[UUID] = mapped_column(
        ForeignKey("delivery_route.id", ondelete="RESTRICT"), index=True
    )
    driver_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT"), index=True
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT"), index=True
    )
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    position: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    accuracy_meters: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
