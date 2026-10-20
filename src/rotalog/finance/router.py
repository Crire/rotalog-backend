from uuid import UUID

from fastapi import APIRouter

from rotalog.finance import service
from rotalog.finance.schemas import FinancialSummary, PaymentResponse
from rotalog.identity.dependencies import CurrentUser, SessionFactory

router = APIRouter(tags=["financeiro simulado"])


@router.get("/purchases/{purchase_id}/payments", response_model=list[PaymentResponse])
def payments(
    purchase_id: UUID, actor: CurrentUser, factory: SessionFactory
) -> list[dict]:
    return service.payments(purchase_id, actor, factory)


@router.get(
    "/supplier-orders/{order_id}/financial-summary", response_model=FinancialSummary
)
def summary(order_id: UUID, actor: CurrentUser, factory: SessionFactory) -> dict:
    return service.financial_summary(order_id, actor, factory)
