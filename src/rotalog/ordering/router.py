from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query

from rotalog.core.contracts import Page, Versioned
from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.ordering import service
from rotalog.ordering.schemas import (
    Acceptance,
    Cancellation,
    CheckoutCreate,
    CheckoutResponse,
    FulfillmentCreate,
    FulfillmentResponse,
    PaymentConfirmationResponse,
    PurchaseResponse,
    SeparationResults,
    SupplierOrderResponse,
)

router = APIRouter(tags=["compras e pedidos"])
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("/checkouts", status_code=201, response_model=CheckoutResponse)
def checkout(
    data: CheckoutCreate,
    key: IdempotencyKey,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.create_checkout(data, key, actor, factory)


@router.get("/checkouts/{checkout_id}", response_model=CheckoutResponse)
def get_checkout(
    checkout_id: UUID, actor: CurrentUser, factory: SessionFactory
) -> dict:
    return service.get_checkout(checkout_id, actor, factory)


@router.post(
    "/checkouts/{checkout_id}/confirm-payment",
    response_model=PaymentConfirmationResponse,
)
def payment(
    checkout_id: UUID,
    data: Versioned,
    key: IdempotencyKey,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.confirm_payment(
        checkout_id, data.expected_version, key, actor, factory
    )


@router.get("/purchases", response_model=Page[PurchaseResponse])
def purchases(
    actor: CurrentUser,
    factory: SessionFactory,
    page: PageNumber = 1,
    page_size: PageSize = 25,
):
    return service.purchases(actor, factory, page, page_size)


@router.get("/purchases/{purchase_id}", response_model=PurchaseResponse)
def purchase(purchase_id: UUID, actor: CurrentUser, factory: SessionFactory) -> dict:
    return service.purchases(actor, factory, 1, 25, purchase_id)


@router.get("/supplier-orders", response_model=Page[SupplierOrderResponse])
def orders(
    actor: CurrentUser,
    factory: SessionFactory,
    page: PageNumber = 1,
    page_size: PageSize = 25,
):
    return service.list_orders(actor, factory, page, page_size)


@router.get("/supplier-orders/{order_id}", response_model=SupplierOrderResponse)
def order(order_id: UUID, actor: CurrentUser, factory: SessionFactory) -> dict:
    return service.get_order(order_id, actor, factory)


@router.post(
    "/supplier-orders/{order_id}/acceptance", response_model=SupplierOrderResponse
)
def acceptance(
    order_id: UUID,
    data: Acceptance,
    key: IdempotencyKey,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.acceptance(order_id, data, key, actor, factory)


@router.post("/supplier-orders/{order_id}/cancel", response_model=SupplierOrderResponse)
def cancel(
    order_id: UUID, data: Cancellation, actor: CurrentUser, factory: SessionFactory
) -> dict:
    return service.cancel_order(order_id, data, actor, factory)


@router.post(
    "/supplier-orders/{order_id}/start-separation", response_model=SupplierOrderResponse
)
def start(
    order_id: UUID, data: Versioned, actor: CurrentUser, factory: SessionFactory
) -> dict:
    return service.start_separation(order_id, data.expected_version, actor, factory)


@router.post(
    "/supplier-orders/{order_id}/fulfillments",
    status_code=201,
    response_model=FulfillmentResponse,
)
def fulfillment(
    order_id: UUID, data: FulfillmentCreate, actor: CurrentUser, factory: SessionFactory
) -> dict:
    return service.create_fulfillment(order_id, data, actor, factory)


@router.post(
    "/fulfillments/{fulfillment_id}/separation-results",
    response_model=FulfillmentResponse,
)
def separation(
    fulfillment_id: UUID,
    data: SeparationResults,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.separation(
        fulfillment_id, data, data.expected_version, actor, factory
    )


@router.post(
    "/fulfillments/{fulfillment_id}/mark-ready", response_model=FulfillmentResponse
)
def ready(
    fulfillment_id: UUID, data: Versioned, actor: CurrentUser, factory: SessionFactory
) -> dict:
    return service.separation(
        fulfillment_id, None, data.expected_version, actor, factory
    )
