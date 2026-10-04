from fastapi import FastAPI

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import Settings


def register_routes(app: FastAPI, settings: Settings) -> None:
    app.include_router(health_router, prefix="/health", tags=["System"])
    app.include_router(api_router, prefix=settings.api_v1_prefix)
