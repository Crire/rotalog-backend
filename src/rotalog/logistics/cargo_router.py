"""Contratos aditivos: conferência não altera as chamadas legadas de coleta."""

from uuid import UUID

from fastapi import APIRouter, Request

from rotalog.core.contracts import Versioned
from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.logistics import cargo_service
from rotalog.logistics.cargo_schemas import (
    CargoCheck,
    CargoIssueCreate,
    CargoIssueResolve,
    CargoManifest,
    CargoReceipt,
)
from rotalog.logistics.delivery_router import Key

router = APIRouter(tags=["manifesto e conferência pré-coleta"])


@router.get("/routes/{route_id}/manifest", response_model=CargoManifest)
def manifest(route_id: UUID, actor: CurrentUser, factory: SessionFactory):
    return cargo_service.get_manifest(route_id, actor, factory)


@router.post("/routes/{route_id}/cargo-inspection", response_model=CargoManifest)
def begin(
    route_id: UUID,
    data: Versioned,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    request: Request,
):
    return cargo_service.cargo_command(
        route_id,
        "begin",
        data,
        key,
        actor,
        factory,
        request_id=request.state.request_id,
    )


@router.post("/routes/{route_id}/cargo-checks", response_model=CargoManifest)
def check(
    route_id: UUID,
    data: CargoCheck,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    request: Request,
):
    return cargo_service.cargo_command(
        route_id,
        "check",
        data,
        key,
        actor,
        factory,
        request_id=request.state.request_id,
    )


@router.post(
    "/routes/{route_id}/cargo-issues", status_code=201, response_model=CargoManifest
)
def report(
    route_id: UUID,
    data: CargoIssueCreate,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    request: Request,
):
    return cargo_service.cargo_command(
        route_id,
        "report",
        data,
        key,
        actor,
        factory,
        request_id=request.state.request_id,
    )


@router.post(
    "/routes/{route_id}/cargo-issues/{issue_id}/resolve", response_model=CargoManifest
)
def resolve(
    route_id: UUID,
    issue_id: UUID,
    data: CargoIssueResolve,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    request: Request,
):
    return cargo_service.cargo_command(
        route_id,
        "resolve",
        data,
        key,
        actor,
        factory,
        issue_id=issue_id,
        request_id=request.state.request_id,
    )


@router.post("/routes/{route_id}/cargo-receipts", response_model=CargoManifest)
def receipt(
    route_id: UUID,
    data: CargoReceipt,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    request: Request,
):
    return cargo_service.cargo_command(
        route_id,
        "receipt",
        data,
        key,
        actor,
        factory,
        request_id=request.state.request_id,
    )
