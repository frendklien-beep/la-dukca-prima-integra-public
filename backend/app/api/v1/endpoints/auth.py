from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_admin_context, get_optional_admin_context
from app.api.dependencies.database import get_db_session
from app.core.cookies import clear_admin_session_cookie, set_admin_session_cookie
from app.core.csrf import validate_csrf
from app.core.exceptions import CsrfInvalidError, InvalidCredentialsError, RateLimitedError
from app.core.origin import validate_origin
from app.schemas.auth import (
    AdminPublic,
    AdminSessionPublic,
    CsrfData,
    CurrentAdminData,
    LoginData,
    LoginRequest,
    LogoutData,
)
from app.schemas.common import SuccessEnvelope, success_envelope
from app.services.admin_session_service import AuthContext, admin_session_service
from app.services.authentication_service import authentication_service

router = APIRouter()


def session_public(value):
    return AdminSessionPublic(
        remember_me=value.remember_me,
        idle_expires_at=value.idle_expires_at,
        expires_at=value.expires_at,
    )


@router.post("/login", response_model=SuccessEnvelope[LoginData], operation_id="admin_login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    settings = request.app.state.settings
    source = request.client.host if request.client else "unknown"
    decision = request.app.state.login_rate_limiter.check(source, request.app.state.clock.now())
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after)
    result = authentication_service.login(
        db,
        username=payload.username,
        password=payload.password,
        remember_me=payload.remember_me,
        request_id=request.state.request_id,
        settings=settings,
        clock=request.app.state.clock,
    )
    if result.status != "success":
        raise InvalidCredentialsError()
    assert result.admin and result.session and result.raw_session_token and result.raw_csrf_token
    set_admin_session_cookie(response, result.raw_session_token, result.session, settings)
    return success_envelope(
        request.state.request_id,
        LoginData(
            admin=AdminPublic.model_validate(result.admin),
            session=session_public(result.session),
            csrf_token=result.raw_csrf_token,
        ),
    )


@router.get(
    "/me", response_model=SuccessEnvelope[CurrentAdminData], operation_id="get_current_admin"
)
def me(request: Request, context: AuthContext = Depends(get_current_admin_context)):
    return success_envelope(
        request.state.request_id,
        CurrentAdminData(
            admin=AdminPublic.model_validate(context.admin), session=session_public(context.session)
        ),
    )


@router.post("/csrf", response_model=SuccessEnvelope[CsrfData], operation_id="refresh_admin_csrf")
def csrf(
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(get_current_admin_context),
):
    validate_origin(request, request.app.state.settings)
    raw = admin_session_service.rotate_csrf(db, context)
    return success_envelope(
        request.state.request_id,
        CsrfData(csrf_token=raw, session_expires_at=context.session.expires_at),
    )


@router.post("/logout", response_model=SuccessEnvelope[LogoutData], operation_id="admin_logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
    context: AuthContext | None = Depends(get_optional_admin_context),
):
    settings = request.app.state.settings
    if context is not None:
        validate_origin(request, settings)
        if not validate_csrf(request.headers.get("x-csrf-token"), context.session.csrf_token_hash):
            raise CsrfInvalidError()
        admin_session_service.logout(db, context, request.state.request_id, request.app.state.clock)
    clear_admin_session_cookie(response, settings)
    return success_envelope(request.state.request_id, LogoutData())
