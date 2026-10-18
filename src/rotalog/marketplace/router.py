"""Endpoints de leitura do catálogo persistente da demonstração."""

from typing import Annotated

from fastapi import APIRouter, Query

from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.marketplace.schemas import OfferPage
from rotalog.marketplace.service import list_offers

router = APIRouter(tags=["ofertas"])


@router.get("/ofertas", response_model=OfferPage)
@router.get("/offers", response_model=OfferPage, summary="Alias V4.1 de /ofertas")
def offers(
    user: CurrentUser,
    factory: SessionFactory,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OfferPage:
    return list_offers(user, factory, page, page_size)
