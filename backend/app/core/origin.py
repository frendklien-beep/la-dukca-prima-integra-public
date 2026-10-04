from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import OriginForbiddenError


def validate_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if not origin or origin == "null" or origin not in settings.allowed_origins:
        raise OriginForbiddenError()
