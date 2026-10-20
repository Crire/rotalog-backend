from typing import Annotated

from fastapi import APIRouter, Query

from rotalog.core.contracts import Page
from rotalog.identity.dependencies import CurrentUser, SessionFactory
from rotalog.organizations.schemas import SupplierResponse
from rotalog.organizations.service import list_suppliers

router = APIRouter(tags=["organizações"])


@router.get(
    "/suppliers",
    response_model=Page[SupplierResponse],
    description="Extensão de consulta da demo; não expõe usuários ou credenciais.",
)
def suppliers(
    actor: CurrentUser,
    factory: SessionFactory,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    return list_suppliers(actor, factory, page, page_size)
