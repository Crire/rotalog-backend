"""Composição dos routers de negócio da API."""

from fastapi import APIRouter

from rotalog.identity.router import router as identity_router

router = APIRouter()
router.include_router(identity_router)
