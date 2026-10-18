"""Contrato de ofertas sintéticas; valores monetários são strings decimais."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
