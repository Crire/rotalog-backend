"""Dependências FastAPI do módulo de identidade."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker

from rotalog.core.config import Settings
from rotalog.identity.schemas import UserResponse
from rotalog.identity.service import authenticate

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


def application_settings(request: Request) -> Settings:
    return request.app.state.settings


def application_sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    factory: Annotated[sessionmaker[Session], Depends(application_sessions)],
    settings: Annotated[Settings, Depends(application_settings)],
) -> UserResponse:
    return authenticate(token, factory, settings)


CurrentUser = Annotated[UserResponse, Depends(current_user)]
SessionFactory = Annotated[sessionmaker[Session], Depends(application_sessions)]
ApplicationSettings = Annotated[Settings, Depends(application_settings)]
