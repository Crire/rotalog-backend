"""Endpoints HTTP de rastreamento de entregas."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header

from rotalog.core.contracts import Versioned
from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.logistics import service
from rotalog.logistics.schemas import (
    DeliveryRouteCreate,
    DeliveryRouteResponse,
    LastLocationResponse,
    LocationCreate,
    LocationResponse,
)

router = APIRouter(tags=["logística e rastreamento"])
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
]


@router.post(
    "/supplier-orders/{order_id}/delivery-route",
    response_model=DeliveryRouteResponse,
    status_code=201,
)
def create_delivery_route(
    order_id: UUID,
    data: DeliveryRouteCreate,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.create_route(order_id, data, actor, factory)


@router.get("/driver/delivery-routes", response_model=list[DeliveryRouteResponse])
def driver_routes(actor: CurrentUser, factory: SessionFactory) -> list[dict]:
    return service.list_driver_routes(actor, factory)


@router.post(
    "/driver/delivery-routes/{route_id}/start",
    response_model=DeliveryRouteResponse,
)
def start_delivery_route(
    route_id: UUID,
    data: Versioned,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.start_route(route_id, data.expected_version, actor, factory)


@router.post(
    "/driver/delivery-routes/{route_id}/complete",
    response_model=DeliveryRouteResponse,
)
def complete_delivery_route(
    route_id: UUID,
    data: Versioned,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.complete_route(route_id, data.expected_version, actor, factory)


@router.post(
    "/driver/delivery-routes/{route_id}/locations",
    response_model=LocationResponse,
    status_code=201,
)
def send_location(
    route_id: UUID,
    data: LocationCreate,
    key: IdempotencyKey,
    actor: CurrentUser,
    factory: SessionFactory,
) -> dict:
    return service.record_location(route_id, data, key, actor, factory)


@router.get(
    "/delivery-routes/{route_id}/location", response_model=LastLocationResponse
)
def get_last_location(
    route_id: UUID, actor: CurrentUser, factory: SessionFactory
) -> dict:
    return service.last_location(route_id, actor, factory)
