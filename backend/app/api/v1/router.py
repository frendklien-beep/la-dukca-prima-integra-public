from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.system import router as system_router
from app.api.v1.routes.admin_dashboard import router as admin_dashboard_router
from app.api.v1.routes.admin_documents import router as admin_documents_router
from app.api.v1.routes.admin_settings import router as admin_settings_router
from app.api.v1.routes.public_chat import router as public_chat_router

api_router = APIRouter()
api_router.include_router(system_router, prefix="/system", tags=["System"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(admin_dashboard_router, prefix="/admin", tags=["Admin Dashboard"])
api_router.include_router(admin_settings_router, prefix="/admin", tags=["Admin Settings"])
api_router.include_router(admin_documents_router, prefix="/admin", tags=["Admin Documents"])

api_router.include_router(public_chat_router, tags=["Public Chat"])
