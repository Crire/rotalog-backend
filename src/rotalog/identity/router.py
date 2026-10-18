"""Endpoints HTTP do módulo de identidade."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm

from rotalog.identity.dependencies import (
    ApplicationSettings,
    CurrentUser,
    SessionFactory,
)
from rotalog.identity.schemas import RegisterRequest, TokenResponse, UserResponse
from rotalog.identity.service import login, register

router = APIRouter(prefix="/auth", tags=["autenticação"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register_user(
    data: RegisterRequest,
    factory: SessionFactory,
    settings: ApplicationSettings,
) -> UserResponse:
    """Cadastra comprador/fornecedor sintético, com uma organização nova na demo ativa."""
    return register(data, factory, settings)


@router.post("/login", response_model=TokenResponse, summary="Login da demonstração")
def authenticate_user(
    response: Response,
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    factory: SessionFactory,
    settings: ApplicationSettings,
) -> TokenResponse:
    """Use o email sintético no campo `username` e a senha escolhida no seed."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return login(credentials.username, credentials.password, factory, settings)


@router.get("/me", response_model=UserResponse)
def profile(user: CurrentUser) -> UserResponse:
    return user
