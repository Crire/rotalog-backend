"""Produtos-variante e ofertas; dinheiro persistido exclusivamente em centavos."""

from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rotalog.core.database import Base, TimestampMixin, UuidPrimaryKeyMixin


class Product(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint(
            "publication_state IN ('DRAFT', 'PUBLISHED')",
            name="publication_state_valid",
        ),
        CheckConstraint(
            "net_content IS NULL OR net_content > 0", name="net_content_positive"
        ),
        CheckConstraint(
            "packaging_quantity IS NULL OR packaging_quantity > 0",
            name="packaging_quantity_positive",
        ),
        CheckConstraint(
            "gross_weight_grams IS NULL OR gross_weight_grams > 0",
            name="weight_positive",
        ),
        CheckConstraint("volume_cm3 IS NULL OR volume_cm3 > 0", name="volume_positive"),
    )
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200))
    gtin: Mapped[str | None] = mapped_column(String(14))
    net_content: Mapped[int | None] = mapped_column(Integer)
    net_content_unit: Mapped[str | None] = mapped_column(String(10))
    packaging_type: Mapped[str | None] = mapped_column(String(100))
    packaging_quantity: Mapped[int | None] = mapped_column(Integer)
    gross_weight_grams: Mapped[int | None] = mapped_column(Integer)
    volume_cm3: Mapped[int | None] = mapped_column(Integer)
    variant_attributes: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    publication_state: Mapped[str] = mapped_column(
        String(20), default="DRAFT", server_default="DRAFT"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    demo_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("demo_run.id", ondelete="RESTRICT"), index=True
    )


class Offer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer"
    __table_args__ = (
        CheckConstraint(
            "minimum_order_quantity > 0", name="minimum_order_quantity_positive"
        ),
        CheckConstraint("amount_minor >= 0", name="amount_non_negative"),
        CheckConstraint("currency = 'BRL'", name="currency_brl"),
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("product.id", ondelete="RESTRICT"), index=True
    )
    supplier_organization_id: Mapped[UUID] = mapped_column(Uuid(), index=True)
    warehouse_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("warehouse.id", ondelete="RESTRICT")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")
    minimum_order_quantity: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    demo_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("demo_run.id", ondelete="RESTRICT"), index=True
    )


class OfferPriceVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_price_version"
    __table_args__ = (
        UniqueConstraint("offer_id", "version"),
        CheckConstraint("amount_minor >= 0", name="amount_non_negative"),
        CheckConstraint(
            "minimum_order_quantity > 0", name="minimum_order_quantity_positive"
        ),
    )
    offer_id: Mapped[UUID] = mapped_column(ForeignKey("offer.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL", server_default="BRL")
    minimum_order_quantity: Mapped[int] = mapped_column(Integer)
