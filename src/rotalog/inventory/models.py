from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class Warehouse(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "warehouse"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_valid"
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_valid",
        ),
    )
    supplier_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500))
    opening_hours: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(100))
    geocoding_state: Mapped[str] = mapped_column(
        String(30), default="PENDING", server_default="PENDING"
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    geocoding_review_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class InventoryProjection(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_projection"
    __table_args__ = (
        UniqueConstraint("offer_id", "warehouse_id"),
        CheckConstraint(
            "external_sellable_quantity >= 0", name="sellable_non_negative"
        ),
        CheckConstraint(
            "external_physical_quantity IS NULL OR external_physical_quantity >= 0",
            name="physical_non_negative",
        ),
        CheckConstraint(
            "rotalog_reserved_not_reflected_quantity >= 0", name="reserved_non_negative"
        ),
        CheckConstraint("safety_stock_quantity >= 0", name="safety_non_negative"),
        CheckConstraint(
            "rotalog_reserved_not_reflected_quantity + safety_stock_quantity <= external_sellable_quantity",
            name="reserved_within_sellable",
        ),
    )
    offer_id: Mapped[UUID] = mapped_column(ForeignKey("offer.id", ondelete="CASCADE"))
    warehouse_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("warehouse.id", ondelete="RESTRICT")
    )
    external_physical_quantity: Mapped[int | None] = mapped_column(Integer)
    external_sellable_quantity: Mapped[int] = mapped_column(Integer)
    rotalog_reserved_not_reflected_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    safety_stock_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    external_version: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(
        String(20), default="MANUAL", server_default="MANUAL"
    )
    freshness_state: Mapped[str] = mapped_column(
        String(20), default="FRESH", server_default="FRESH"
    )
    source_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("demo_run.id", ondelete="RESTRICT"), index=True
    )

    @property
    def effective_sellable_quantity(self) -> int:
        return max(
            0,
            self.external_sellable_quantity
            - self.rotalog_reserved_not_reflected_quantity
            - self.safety_stock_quantity,
        )


class InventoryAdjustment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Movimento nominal preservado; não substitui a auditoria global futura."""

    __tablename__ = "inventory_adjustment"
    projection_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_projection.id", ondelete="RESTRICT")
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_user.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(String(500))
    before_quantity: Mapped[int] = mapped_column(Integer)
    after_quantity: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)


class CapacitySlot(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "capacity_slot"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="window_valid"),
        CheckConstraint(
            "total_quantity >= reserved_quantity AND reserved_quantity >= 0",
            name="quantities_valid",
        ),
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        ForeignKey("warehouse.id", ondelete="RESTRICT")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_quantity: Mapped[int] = mapped_column(Integer)
    reserved_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    adjustments: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")


class Reservation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reservation"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "released_quantity >= 0 AND released_quantity <= quantity",
            name="released_valid",
        ),
    )
    checkout_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_session.id", ondelete="RESTRICT")
    )
    projection_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_projection.id", ondelete="RESTRICT")
    )
    capacity_slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("capacity_slot.id", ondelete="RESTRICT")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    released_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", server_default="ACTIVE"
    )
    origin: Mapped[str] = mapped_column(
        String(20), default="CHECKOUT", server_default="CHECKOUT"
    )
