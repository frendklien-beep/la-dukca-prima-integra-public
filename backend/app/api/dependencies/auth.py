from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db_session
from app.core.exceptions import AuthRequiredError, SessionExpiredError
from app.services.admin_session_service import AuthContext, admin_session_service


def get_optional_admin_context(
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthContext | None:
    settings = request.app.state.settings
    raw_token = request.cookies.get(settings.admin_session_cookie_name)
    if not raw_token:
        return None

    context = admin_session_service.resolve(
        db,
        raw_token,
        request.app.state.clock,
        settings,
    )
    if db.in_transaction():
        db.commit()
    return context


def get_current_admin_context(
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthContext:
    settings = request.app.state.settings
    raw_token = request.cookies.get(settings.admin_session_cookie_name)
    if not raw_token:
        raise AuthRequiredError()

    context = admin_session_service.resolve(
        db,
        raw_token,
        request.app.state.clock,
        settings,
    )
    if context is None:
        if db.in_transaction():
            db.rollback()
        raise SessionExpiredError()

    if db.in_transaction():
        db.commit()
    return context
