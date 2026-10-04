from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthContext, get_current_admin_context
from app.api.dependencies.database import get_db_session
from app.api.dependencies.security import require_admin_mutation_context
from app.api.v1.routes._mappers import settings_data
from app.schemas.common import success_envelope
from app.schemas.settings import AdminSettingsResponse, SettingsUpdateRequest
from app.services.settings_service import settings_service

router = APIRouter()


@router.get(
    "/settings",
    response_model=AdminSettingsResponse,
    operation_id="admin_get_settings",
    summary="Baca pengaturan AI yang aman",
)
def get_settings_route(
    request: Request,
    db: Session = Depends(get_db_session),
    _context: AuthContext = Depends(get_current_admin_context),
):
    snapshot = settings_service.get_snapshot(db, request.app.state.settings)
    return success_envelope(request.state.request_id, settings_data(snapshot))


@router.patch(
    "/settings",
    response_model=AdminSettingsResponse,
    operation_id="admin_update_settings",
    summary="Perbarui pengaturan AI yang diizinkan",
)
def update_settings_route(
    payload: SettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(require_admin_mutation_context),
):
    submitted = payload.model_dump(exclude_unset=True)
    snapshot = settings_service.update(
        db,
        submitted=submitted,
        admin_id=context.admin.id,
        request_id=request.state.request_id,
        settings=request.app.state.settings,
    )
    return success_envelope(request.state.request_id, settings_data(snapshot))
