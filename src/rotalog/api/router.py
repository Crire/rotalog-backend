"""Composição dos routers de negócio da API."""

from fastapi import APIRouter

from rotalog.catalog.router import router as catalog_router
from rotalog.finance.router import router as finance_router
from rotalog.identity.router import router as identity_router
from rotalog.inventory.router import router as inventory_router
from rotalog.logistics.delivery_router import router as delivery_router
from rotalog.logistics.router import router as logistics_router
from rotalog.ordering.router import router as ordering_router
from rotalog.organizations.router import router as organizations_router

router = APIRouter()
router.include_router(identity_router)
router.include_router(catalog_router)
router.include_router(inventory_router)
router.include_router(logistics_router)
router.include_router(delivery_router)
router.include_router(ordering_router)
router.include_router(organizations_router)
router.include_router(finance_router)
