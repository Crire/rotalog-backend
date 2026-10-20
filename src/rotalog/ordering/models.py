"""Compra e pedido independentes; snapshots comerciais imutáveis por linha."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class CheckoutSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "checkout_session"
    buyer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    supplier_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        ForeignKey("warehouse.id", ondelete="RESTRICT")
    )
    capacity_slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("capacity_slot.id", ondelete="RESTRICT")
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(
        String(32), default="READY_FOR_PAYMENT", server_default="READY_FOR_PAYMENT"
    )
    accepts_partial: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class CheckoutLine(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "checkout_line"
    __table_args__ = (
        UniqueConstraint("checkout_id", "offer_id"),
        CheckConstraint("quantity > 0 AND amount_minor >= 0", name="values_valid"),
    )
    checkout_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_session.id", ondelete="RESTRICT")
    )
    offer_id: Mapped[UUID] = mapped_column(ForeignKey("offer.id", ondelete="RESTRICT"))
    offer_version: Mapped[int] = mapped_column(Integer)
    product_snapshot: Mapped[dict] = mapped_column(JSONB)
    quantity: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")


class Purchase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "purchase"
    checkout_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_session.id", ondelete="RESTRICT"), unique=True
    )
    buyer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT")
    )


class SupplierOrder(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "supplier_order"
    purchase_id: Mapped[UUID] = mapped_column(
        ForeignKey("purchase.id", ondelete="RESTRICT")
    )
    buyer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    supplier_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        ForeignKey("warehouse.id", ondelete="RESTRICT")
    )
    demo_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_run.id", ondelete="RESTRICT")
    )
    state: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    accepts_partial: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    acceptance_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")


class OrderItem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_item"
    __table_args__ = (
        CheckConstraint(
            "requested_quantity > 0 AND amount_minor >= 0", name="snapshot_valid"
        ),
        CheckConstraint(
            "supplier_accepted_quantity >= 0 AND supplier_refused_quantity >= 0 AND supplier_accepted_quantity + supplier_refused_quantity <= requested_quantity",
            name="decision_valid",
        ),
        CheckConstraint(
            "reserved_quantity >= 0 AND reserved_quantity <= requested_quantity",
            name="reservation_valid",
        ),
    )
    supplier_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("supplier_order.id", ondelete="RESTRICT")
    )
    offer_id: Mapped[UUID] = mapped_column(ForeignKey("offer.id", ondelete="RESTRICT"))
    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("reservation.id", ondelete="RESTRICT"), unique=True
    )
    product_snapshot: Mapped[dict] = mapped_column(JSONB)
    offer_version: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")
    requested_quantity: Mapped[int] = mapped_column(Integer)
    reserved_quantity: Mapped[int] = mapped_column(Integer)
    supplier_accepted_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    supplier_refused_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )


class Fulfillment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fulfillment"
    supplier_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("supplier_order.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        ForeignKey("warehouse.id", ondelete="RESTRICT")
    )
    state: Mapped[str] = mapped_column(
        String(32), default="SEPARATING", server_default="SEPARATING"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class FulfillmentLine(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fulfillment_line"
    __table_args__ = (
        UniqueConstraint("fulfillment_id", "order_item_id"),
        CheckConstraint(
            "allocated_quantity > 0 AND separated_quantity >= 0 AND separated_quantity <= allocated_quantity AND dispatched_quantity >= 0 AND dispatched_quantity <= separated_quantity",
            name="quantities_valid",
        ),
    )
    fulfillment_id: Mapped[UUID] = mapped_column(
        ForeignKey("fulfillment.id", ondelete="RESTRICT")
    )
    order_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("order_item.id", ondelete="RESTRICT")
    )
    allocated_quantity: Mapped[int] = mapped_column(Integer)
    separated_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    dispatched_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
