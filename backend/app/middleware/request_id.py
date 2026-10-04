import logging
import re
from typing import Any
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import reset_request_id, set_request_id
from app.schemas.error import error_envelope

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
logger = logging.getLogger(__name__)


def resolve_request_id(value: str | None) -> str:
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id")
        request_id = resolve_request_id(incoming)
        scope.setdefault("state", {})["request_id"] = request_id
        token = set_request_id(request_id)
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["Cache-Control"] = "no-store"
                headers["Pragma"] = "no-cache"
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            if response_started:
                raise
            logger.exception("unhandled_exception")
            payload = error_envelope(
                request_id=request_id,
                code="INTERNAL_SERVER_ERROR",
                message="Terjadi kendala pada sistem. Silakan coba kembali.",
                retryable=True,
            )
            response = JSONResponse(status_code=500, content=payload.model_dump(mode="json"))
            await response(scope, receive, send_with_headers)
        finally:
            reset_request_id(token)


def register_middleware(app: Any) -> None:
    app.add_middleware(RequestIDMiddleware)
