"""Endpoints do catálogo e estoque sintéticos; regras permanecem nos serviços."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.marketplace.schemas import (
    InventoryResponse,
    InventoryUpdate,
    OfferCreate,
    OfferPage,
    OfferResponse,
    ProductCreate,
    ProductResponse,
)
from rotalog.marketplace.service import (
    create_offer,
    create_product,
    get_inventory,
    list_offers,
    update_inventory,
)

router = APIRouter(tags=["ofertas"])


@router.post("/products", response_model=ProductResponse, status_code=201)
def register_product(
    data: ProductCreate,
    user: CurrentUser,
    factory: SessionFactory,
) -> ProductResponse:
    return create_product(data, user, factory)


@router.post("/ofertas", response_model=OfferResponse, status_code=201)
@router.post("/offers", response_model=OfferResponse, status_code=201)
def register_offer(
    data: OfferCreate,
    user: CurrentUser,
    factory: SessionFactory,
) -> OfferResponse:
    """Cria oferta e saldo inicial na organização do fornecedor autenticado."""
    return create_offer(data, user, factory)


@router.get("/ofertas/{offer_id}/estoque", response_model=InventoryResponse)
@router.get("/offers/{offer_id}/inventory", response_model=InventoryResponse)
def inventory(
    offer_id: UUID,
    user: CurrentUser,
    factory: SessionFactory,
) -> InventoryResponse:
    return get_inventory(offer_id, user, factory)


@router.patch("/ofertas/{offer_id}/estoque", response_model=InventoryResponse)
@router.patch("/offers/{offer_id}/inventory", response_model=InventoryResponse)
def adjust_inventory(
    offer_id: UUID,
    data: InventoryUpdate,
    user: CurrentUser,
    factory: SessionFactory,
) -> InventoryResponse:
    """Define o estoque total declarado. Não aceita alterações das reservas."""
    return update_inventory(offer_id, data, user, factory)


@router.get("/ofertas", response_model=OfferPage)
@router.get("/offers", response_model=OfferPage, summary="Alias V4.1 de /ofertas")
def offers(
    user: CurrentUser,
    factory: SessionFactory,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OfferPage:
    return list_offers(user, factory, page, page_size)
