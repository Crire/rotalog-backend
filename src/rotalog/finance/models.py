from uuid import UUID

from sqlalchemy import CHAR, BigInteger, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class Payment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment"
    __table_args__ = (CheckConstraint("amount_minor >= 0", name="amount_non_negative"),)
    purchase_id: Mapped[UUID] = mapped_column(
        ForeignKey("purchase.id", ondelete="RESTRICT"), unique=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")
    state: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(
        String(20), default="SIMULATED", server_default="SIMULATED"
    )


class PaymentAllocation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_allocation"
    __table_args__ = (
        CheckConstraint("amount_minor >= 0 AND quantity > 0", name="values_valid"),
        CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= amount_minor",
            name="refund_valid",
        ),
        CheckConstraint(
            "refunded_quantity >= 0 AND refunded_quantity <= quantity",
            name="refunded_quantity_valid",
        ),
    )
    payment_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment.id", ondelete="RESTRICT")
    )
    order_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("order_item.id", ondelete="RESTRICT"), unique=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")
    quantity: Mapped[int] = mapped_column(Integer)
    refunded_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    refunded_minor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )
    state: Mapped[str] = mapped_column(
        String(20), default="PROTECTED", server_default="PROTECTED"
    )
