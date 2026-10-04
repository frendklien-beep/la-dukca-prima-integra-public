from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    reason: str
    message: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[ErrorDetail]
    request_id: str
    retryable: bool


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


def error_envelope(
    *,
    request_id: str,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
    retryable: bool,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
            retryable=retryable,
        )
    )
