from fastapi import APIRouter, Request

from app.schemas.common import SuccessEnvelope, success_envelope
from app.schemas.system import LivenessData, ReadinessData
from app.services.health_service import get_readiness

router = APIRouter()


@router.get(
    "/live",
    response_model=SuccessEnvelope[LivenessData],
    operation_id="get_liveness",
    summary="Liveness check",
)
def get_liveness(request: Request):
    return success_envelope(
        request.state.request_id, LivenessData(service=request.app.state.settings.service_name)
    )


@router.get(
    "/ready",
    response_model=SuccessEnvelope[ReadinessData],
    operation_id="get_readiness",
    summary="Readiness check",
)
def readiness(request: Request):
    return success_envelope(
        request.state.request_id,
        get_readiness(request.app.state.settings, request.app.state.engine),
    )
