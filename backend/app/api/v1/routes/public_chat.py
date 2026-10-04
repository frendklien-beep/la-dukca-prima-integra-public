from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatResponseData,
    ChatSourceCard,
    CloseSessionData,
    CloseSessionResponse,
)
from app.schemas.common import success_envelope

router = APIRouter()


def build_public_client_key(request: Request, session_id: UUID | None) -> str:
    if session_id is not None:
        material = f"session:{session_id}"
    else:
        host = request.client.host if request.client else "unknown"
        material = f"network:{host}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@router.post(
    "/chat",
    response_model=ChatResponse,
    operation_id="publicChatSendMessage",
    summary="Kirim pertanyaan konsultasi publik",
)
async def send_chat_message(payload: ChatRequest, request: Request, response: Response):
    result = await request.app.state.chat_service.send_message(
        message=payload.message,
        session_id=payload.session_id,
        request_id=request.state.request_id,
        client_key=build_public_client_key(request, payload.session_id),
        now_utc=request.app.state.clock.now(),
    )
    response.headers["Cache-Control"] = "no-store"
    return success_envelope(
        request.state.request_id,
        ChatResponseData(
            session_id=result.session_id,
            message_id=result.message_id,
            status=result.status,
            answer=result.answer,
            sources=[
                ChatSourceCard(
                    title=source.title,
                    page_start=source.page_start,
                    page_end=source.page_end,
                    section=source.section,
                    reference_label=source.reference_label,
                )
                for source in result.sources
            ],
            fallback_reason=result.fallback_reason,
            privacy_notice=result.privacy_notice,
        ),
    )


@router.post(
    "/chat/sessions/{session_id}/close",
    response_model=CloseSessionResponse,
    operation_id="publicChatCloseSession",
    summary="Tutup sesi chat publik",
)
def close_chat_session(session_id: UUID, request: Request, response: Response):
    request.app.state.chat_service.close_session(
        session_id=session_id,
        now_utc=request.app.state.clock.now(),
    )
    response.headers["Cache-Control"] = "no-store"
    return success_envelope(
        request.state.request_id,
        CloseSessionData(session_id=session_id),
    )
