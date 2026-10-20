from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PaymentResponse(BaseModel):
    id: UUID
    amount: str
    currency: Literal["BRL"]
    state: str
    provider: Literal["SIMULATED"]
    is_synthetic: Literal[True]


class FinancialSummary(BaseModel):
    supplier_order_id: UUID
    currency: Literal["BRL"]
    captured: str
    refunded: str
    protected: str
    released: str
    provider: Literal["SIMULATED"]
    is_synthetic: Literal[True]
