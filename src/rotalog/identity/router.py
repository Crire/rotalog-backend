"""Endpoints HTTP do módulo de identidade."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["autenticação"])
