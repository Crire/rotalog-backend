"""Composição dos routers de negócio da API."""

from fastapi import APIRouter

from rotalog.catalog.image_router import router as image_router
from rotalog.catalog.router import router as catalog_router
from rotalog.finance.router import router as finance_router
from rotalog.identity.router import router as identity_router
from rotalog.inventory.router import router as inventory_router
from rotalog.logistics.cargo_router import router as cargo_router
from rotalog.logistics.delivery_router import router as delivery_router
from rotalog.logistics.router import router as logistics_router
from rotalog.logistics.tracking_router import router as tracking_router
from rotalog.operations.file_router import router as file_router
from rotalog.ordering.router import router as ordering_router
from rotalog.organizations.router import router as organizations_router

router = APIRouter()
router.include_router(identity_router)
router.include_router(catalog_router)
router.include_router(image_router)
router.include_router(file_router)
router.include_router(inventory_router)
router.include_router(logistics_router)
router.include_router(delivery_router)
router.include_router(cargo_router)
router.include_router(tracking_router)
router.include_router(ordering_router)
router.include_router(organizations_router)
router.include_router(finance_router)
