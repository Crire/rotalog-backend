from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rotalog.core.contracts import Input, Name, PositiveQuantity, Versioned
from rotalog.core.money import MoneyInput


class ProductCreate(Input):
    name: Name
    brand: Name
    category: Literal["ALIMENTO_SECO_INDUSTRIALIZADO"]
    gtin: Annotated[str, Field(pattern=r"^(?:[0-9]{8}|[0-9]{12,14})$")] | None = None
    net_content: PositiveQuantity
    net_content_unit: Literal["g", "ml", "un"]
    packaging_type: Name
    packaging_quantity: PositiveQuantity
    gross_weight_grams: PositiveQuantity
    volume_cm3: PositiveQuantity
    variant_attributes: dict[str, str] = Field(default_factory=dict, max_length=20)


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    publication_state: str
    version: int
    demo_run_id: UUID
    is_synthetic: Literal[True] = True


class OfferCreate(Input):
    product_id: UUID
    warehouse_id: UUID
    unit_price: MoneyInput
    currency: Literal["BRL"] = "BRL"
    minimum_order_quantity: PositiveQuantity = 1


class PriceChange(Versioned):
    unit_price: MoneyInput
    currency: Literal["BRL"] = "BRL"
    minimum_order_quantity: PositiveQuantity = 1


class OfferResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    supplier_organization_id: UUID
    supplier_name: str
    warehouse_id: UUID
    region: str
    unit_price: str
    currency: Literal["BRL"] = "BRL"
    minimum_order_quantity: int
    available_quantity: int
    version: int
    is_active: bool
    demo_run_id: UUID
    is_synthetic: Literal[True] = True


class OfferFilters(BaseModel):
    product_id: UUID | None = None
    supplier_id: UUID | None = None
    region: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
