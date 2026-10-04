from fastapi import Response

from app.core.config import Settings
from app.models.admin_session import AdminSession


def set_admin_session_cookie(
    response: Response, raw_token: str, session: AdminSession, settings: Settings
) -> None:
    max_age = None
    if session.remember_me:
        max_age = max(0, int((session.expires_at - session.created_at).total_seconds()))
    response.set_cookie(
        key=settings.admin_session_cookie_name,
        value=raw_token,
        max_age=max_age,
        expires=session.expires_at if session.remember_me else None,
        path="/",
        domain=None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def clear_admin_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.admin_session_cookie_name,
        path="/",
        domain=None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
