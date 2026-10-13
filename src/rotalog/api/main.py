from fastapi import FastAPI

from rotalog.api.health import router as health_router
from rotalog.core.config import Settings, get_settings
from rotalog.api.middleware import request_id
from rotalog.api.router import router as api_router

def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria e configura uma instância da API."""

    app_settings = settings or get_settings()
    application = FastAPI(
        title=app_settings.app_name,
        description=app_settings.app_description,
        version=app_settings.app_version,
        debug=app_settings.debug,
    )
    application.state.settings = app_settings
    application.include_router(health_router)
    return application


app = create_app()
app.add_middleware(request_id)
register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")
