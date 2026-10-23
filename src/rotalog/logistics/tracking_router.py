from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from rotalog.identity.dependencies import (
    ApplicationSettings,
    CurrentUser,
    SessionFactory,
)
from rotalog.logistics import tracking_service
from rotalog.logistics.tracking_schemas import (
    BatchResponse,
    TrackingBatch,
    TrackingCurrent,
    TrackingHistory,
    TrackingStatusChange,
)

router = APIRouter(tags=["rastreamento canônico V5"])


@router.post("/routes/{route_id}/location-batches", response_model=BatchResponse)
def batches(
    route_id: UUID,
    data: TrackingBatch,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return tracking_service.ingest(route_id, data, actor, factory, settings)


@router.get("/routes/{route_id}/tracking/current", response_model=TrackingCurrent)
def current(
    route_id: UUID,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return tracking_service.get_current(route_id, actor, factory, settings)


@router.get("/routes/{route_id}/tracking/history", response_model=TrackingHistory)
def history(
    route_id: UUID,
    actor: CurrentUser,
    factory: SessionFactory,
    cursor: Annotated[str | None, Query(max_length=300)] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return tracking_service.get_history(
        route_id, actor, factory, cursor=cursor, page_size=page_size
    )


@router.post("/routes/{route_id}/tracking-status", response_model=TrackingCurrent)
def status(
    route_id: UUID,
    data: TrackingStatusChange,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return tracking_service.change_status(route_id, data, actor, factory, settings)
