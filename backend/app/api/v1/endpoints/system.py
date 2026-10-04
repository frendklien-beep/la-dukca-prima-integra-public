from fastapi import APIRouter, Request

from app.schemas.common import SuccessEnvelope, success_envelope
from app.schemas.system import SystemVersionData
from app.services.system_service import get_system_version

router = APIRouter()


@router.get(
    "/version",
    response_model=SuccessEnvelope[SystemVersionData],
    operation_id="get_system_version",
    summary="Safe system version metadata",
)
def get_version(request: Request) -> SuccessEnvelope[SystemVersionData]:
    return success_envelope(
        request.state.request_id,
        get_system_version(request.app.state.settings),
    )
