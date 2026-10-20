from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from rotalog.core.contracts import Page
from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.inventory import service
from rotalog.inventory.schemas import (
    CapacityAdjustment,
    CapacityCreate,
    CapacityResponse,
    GeocodingReview,
    InventoryAdjustmentRequest,
    InventoryResponse,
    WarehouseCreate,
    WarehouseResponse,
)

router = APIRouter(tags=["estoque e capacidade"])
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "/suppliers/{supplier_id}/warehouses",
    response_model=WarehouseResponse,
    status_code=201,
)
def warehouse(
    supplier_id: UUID,
    data: WarehouseCreate,
    actor: CurrentUser,
    factory: SessionFactory,
):
    return service.create_warehouse(supplier_id, data, actor, factory)


@router.get("/warehouses", response_model=Page[WarehouseResponse])
def warehouses(
    actor: CurrentUser,
    factory: SessionFactory,
    page: PageNumber = 1,
    page_size: PageSize = 25,
):
    return service.list_warehouses(actor, factory, page, page_size)


@router.post(
    "/warehouses/{warehouse_id}/geocoding-review", response_model=WarehouseResponse
)
def review(
    warehouse_id: UUID,
    data: GeocodingReview,
    actor: CurrentUser,
    factory: SessionFactory,
):
    return service.review_geocoding(warehouse_id, data, actor, factory)


@router.get("/inventory", response_model=Page[InventoryResponse])
def inventory(
    actor: CurrentUser,
    factory: SessionFactory,
    warehouse_id: UUID | None = None,
    offer_id: UUID | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
):
    return service.list_inventory(
        actor, factory, page, page_size, warehouse_id, offer_id
    )


@router.post("/inventory/manual-adjustments", response_model=InventoryResponse)
def adjust(
    data: InventoryAdjustmentRequest, actor: CurrentUser, factory: SessionFactory
):
    return service.adjust_inventory(data, actor, factory)


@router.post(
    "/demo/capacity-slots",
    response_model=CapacityResponse,
    status_code=201,
    description="Extensão sintética: cria janela manual; não agenda transporte real.",
)
def create_capacity(data: CapacityCreate, actor: CurrentUser, factory: SessionFactory):
    return service.create_capacity(data, actor, factory)


@router.get("/capacity-slots", response_model=Page[CapacityResponse])
def capacity(
    actor: CurrentUser,
    factory: SessionFactory,
    warehouse_id: UUID | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
):
    return service.list_capacity(actor, factory, warehouse_id, page, page_size)


@router.post("/capacity-slots/{slot_id}/adjustments", response_model=CapacityResponse)
def capacity_adjust(
    slot_id: UUID, data: CapacityAdjustment, actor: CurrentUser, factory: SessionFactory
):
    return service.adjust_capacity(slot_id, data, actor, factory)
