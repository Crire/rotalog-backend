from fastapi import Router

from api.identity import router as identity_router

router = APIRouter()
router.include_router(health_router, prefix="/health", tags=["Health"])