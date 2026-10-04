from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthContext, get_current_admin_context
from app.api.dependencies.database import get_db_session
from app.api.v1.routes._mappers import dashboard_data
from app.schemas.common import success_envelope
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter()


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    operation_id="admin_get_dashboard",
    summary="Ringkasan operasional administrator",
)
def get_dashboard(
    request: Request,
    db: Session = Depends(get_db_session),
    _context: AuthContext = Depends(get_current_admin_context),
):
    snapshot = dashboard_service.get_snapshot(
        session=db,
        settings=request.app.state.settings,
        storage_status=request.app.state.storage_status,
    )
    return success_envelope(request.state.request_id, dashboard_data(snapshot))
