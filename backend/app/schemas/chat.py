from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import SuccessEnvelope


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        cleaned = "".join(
            character if character in "\t\n\r" or ord(character) >= 32 else " "
            for character in value.replace("\x00", " ")
        )
        normalized = " ".join(cleaned.split())
        if not normalized:
            raise ValueError("Pesan tidak boleh kosong.")
        if not any(character.isalnum() for character in normalized):
            raise ValueError("Pesan harus memuat huruf atau angka yang bermakna.")
        return normalized


class ChatSourceCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    page_start: int | None
    page_end: int | None
    section: str | None
    reference_label: str


class ChatResponseData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    message_id: int
    status: Literal[
        "success",
        "insufficient_knowledge",
        "blocked_sensitive_data",
        "out_of_scope",
    ]
    answer: str
    sources: list[ChatSourceCard]
    fallback_reason: str | None
    privacy_notice: str


class ChatResponse(SuccessEnvelope[ChatResponseData]):
    pass


class CloseSessionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    status: Literal["closed"] = "closed"


class CloseSessionResponse(SuccessEnvelope[CloseSessionData]):
    pass
