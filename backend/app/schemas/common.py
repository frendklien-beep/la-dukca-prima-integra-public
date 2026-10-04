from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class ResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    timestamp: datetime

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SuccessEnvelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: T
    meta: ResponseMeta


def utc_now() -> datetime:
    return datetime.now(UTC)


def success_envelope[T](
    request_id: str,
    data: T,
) -> SuccessEnvelope[T]:
    return SuccessEnvelope(
        data=data,
        meta=ResponseMeta(
            request_id=request_id,
            timestamp=utc_now(),
        ),
    )
