from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.conversation import RecentMessage, SourceCard
from app.models.message_source import MessageSource
from app.models.public_chat_message import PublicChatMessage
from app.models.public_chat_session import PublicChatSession


class ChatRepository:
    def resolve_session(
        self,
        session: Session,
        *,
        requested_id: UUID | None,
        now: datetime,
        session_hours: int,
    ) -> tuple[PublicChatSession, bool]:
        entity: PublicChatSession | None = None
        if requested_id is not None:
            entity = session.get(PublicChatSession, str(requested_id))
            if entity is not None and (entity.status != "active" or entity.expires_at <= now):
                if entity.status == "active" and entity.expires_at <= now:
                    entity.status = "expired"
                entity = None
        if entity is not None:
            entity.last_activity_at = now
            entity.expires_at = now + timedelta(hours=session_hours)
            session.flush()
            return entity, False
        entity = PublicChatSession(
            id=str(uuid4()),
            status="active",
            message_count=0,
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(hours=session_hours),
            closed_at=None,
            greeting_sent_at=None,
        )
        session.add(entity)
        session.flush()
        return entity, True

    def recent_messages(
        self, session: Session, session_id: str, limit: int
    ) -> tuple[RecentMessage, ...]:
        rows = tuple(
            session.scalars(
                select(PublicChatMessage)
                .where(PublicChatMessage.session_id == session_id)
                .order_by(PublicChatMessage.id.desc())
                .limit(limit)
            )
        )
        return tuple(RecentMessage(role=row.role, content=row.content) for row in reversed(rows))

    def persist_turn(
        self,
        session: Session,
        *,
        chat_session: PublicChatSession,
        safe_user_content: str,
        assistant_content: str,
        response_status: str,
        error_code: str | None,
        sources: tuple[SourceCard, ...],
        now: datetime,
        claim_greeting: bool,
        session_hours: int,
    ) -> PublicChatMessage:
        user_message = PublicChatMessage(
            session_id=chat_session.id,
            role="user",
            content=safe_user_content,
            response_status=None,
            error_code=None,
            created_at=now,
        )
        assistant_message = PublicChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=assistant_content,
            response_status=response_status,
            error_code=error_code,
            created_at=now,
        )
        session.add_all((user_message, assistant_message))
        session.flush()
        for source in sources:
            session.add(
                MessageSource(
                    message_id=assistant_message.id,
                    document_id=source.document_id,
                    chunk_id=source.chunk_id,
                    title_snapshot=source.title,
                    page_start=source.page_start,
                    page_end=source.page_end,
                    section_snapshot=source.section,
                    relevance_score=source.relevance_score,
                    created_at=now,
                )
            )
        chat_session.message_count += 2
        chat_session.last_activity_at = now
        chat_session.expires_at = now + timedelta(hours=session_hours)
        if claim_greeting and chat_session.greeting_sent_at is None:
            chat_session.greeting_sent_at = now
        session.flush()
        return assistant_message

    def close_session(self, session: Session, session_id: UUID, now: datetime) -> None:
        entity = session.get(PublicChatSession, str(session_id))
        if entity is None or entity.status == "closed":
            return
        entity.status = "closed"
        entity.closed_at = now
        entity.last_activity_at = now
        session.flush()
