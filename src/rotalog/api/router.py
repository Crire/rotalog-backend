"""Composição dos routers de negócio da API."""

from fastapi import APIRouter

from rotalog.identity.router import router as identity_router
from rotalog.marketplace.router import router as marketplace_router

router = APIRouter()
router.include_router(identity_router)
router.include_router(marketplace_router)
