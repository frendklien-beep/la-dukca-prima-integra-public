from fastapi import APIRouter

from app.api.v1.endpoints.system import router as system_router
from app.api.v1.routes.public_chat import router as public_chat_router

api_router = APIRouter()
api_router.include_router(system_router, prefix="/system", tags=["System"])
api_router.include_router(public_chat_router, tags=["Public Chat"])
