import logging

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.schemas.error import ErrorDetail, error_envelope

logger = logging.getLogger(__name__)


def _request_id(r):
    return getattr(r.state, "request_id", "-")


def _json_error(
    *, request_id, code, message, status_code, details=None, retryable=False, headers=None
):
    payload = error_envelope(
        request_id=request_id, code=code, message=message, details=details, retryable=retryable
    )
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json"), headers=headers or {}
    )


async def app_error_handler(request, exc):
    return _json_error(
        request_id=_request_id(request),
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        retryable=exc.retryable,
        headers=exc.headers,
    )


async def validation_error_handler(request, exc):
    details = []
    for error in exc.errors():
        loc = [str(x) for x in error.get("loc", ()) if x != "body"]
        details.append(
            ErrorDetail(
                field=".".join(loc) or None,
                reason=str(error.get("type", "invalid")),
                message=str(error.get("msg", "Nilai tidak valid.")),
            )
        )
    return _json_error(
        request_id=_request_id(request),
        code="VALIDATION_ERROR",
        message="Data yang dikirim belum sesuai.",
        status_code=422,
        details=details,
    )


async def http_exception_handler(request, exc):
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    messages = {
        404: "Rute atau sumber tidak ditemukan.",
        405: "Metode HTTP tidak diizinkan untuk rute ini.",
    }
    return _json_error(
        request_id=_request_id(request),
        code=codes.get(exc.status_code, "HTTP_ERROR"),
        message=messages.get(exc.status_code, "Permintaan tidak dapat diproses."),
        status_code=exc.status_code,
    )


async def generic_exception_handler(request, exc):
    logger.exception("unhandled_exception")
    return _json_error(
        request_id=_request_id(request),
        code="INTERNAL_SERVER_ERROR",
        message="Terjadi kendala pada sistem. Silakan coba kembali.",
        status_code=500,
        retryable=True,
    )


def register_exception_handlers(app):
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
