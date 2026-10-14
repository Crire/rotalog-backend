"""Bootstrap da aplicação FastAPI."""

from fastapi import FastAPI

from rotalog.api.exception_handler import (
    DEFAULT_ERROR_RESPONSES,
    register_exception_handlers,
)
from rotalog.api.health import router as health_router
from rotalog.api.middleware.request_id import RequestIDMiddleware
from rotalog.api.router import router as api_router
from rotalog.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria e configura uma instância da API."""

    app_settings = settings or get_settings()
    application = FastAPI(
        title=app_settings.app_name,
        description=app_settings.app_description,
        version=app_settings.app_version,
        debug=app_settings.debug,
        responses=DEFAULT_ERROR_RESPONSES,
    )
    application.state.settings = app_settings
    application.add_middleware(RequestIDMiddleware)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
