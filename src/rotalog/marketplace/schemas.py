"""Contrato de ofertas sintéticas; valores monetários são strings decimais."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Quantity = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    demo_run_id: UUID
    is_synthetic: Literal[True] = True


class OfferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    unit_price: Decimal = Field(
        ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False
    )
    minimum_order_quantity: int = Field(default=1, strict=True, ge=1, le=2_147_483_647)
    available_quantity: Quantity = 0


class InventoryUpdate(BaseModel):
    """Saldo total declarado; reservas só podem ser alteradas pelo caso de uso de reserva."""

    model_config = ConfigDict(extra="forbid")

    available_quantity: Quantity


class InventoryResponse(BaseModel):
    offer_id: UUID
    declared_quantity: int
    reserved_quantity: int
    available_quantity: int
    demo_run_id: UUID
    is_synthetic: Literal[True] = True


class OfferResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    supplier_organization_id: UUID
    supplier_name: str
    unit_price: Decimal
    minimum_order_quantity: int
    available_quantity: int
    demo_run_id: UUID
    is_synthetic: Literal[True] = True


class OfferPage(BaseModel):
    items: list[OfferResponse]
    total: int
    page: int
    page_size: int
    is_synthetic: Literal[True] = True
    label: Literal["SIMULAÇÃO — dados sintéticos"] = Field(
        default="SIMULAÇÃO — dados sintéticos",
    )
