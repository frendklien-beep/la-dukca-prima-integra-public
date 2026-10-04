from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.knowledge.types import PreparedChunk


class ProcessingRepository:
    def claim_pending(self, session: Session, document_id: int, now: datetime) -> bool:
        result = session.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.processing_status == "pending",
                Document.archived_at.is_(None),
            )
            .values(
                processing_status="processing",
                processing_started_at=now,
                processing_error_code=None,
                processing_error_message=None,
                updated_at=now,
            )
        )
        return result.rowcount == 1

    def get_document(self, session: Session, document_id: int) -> Document | None:
        return session.get(Document, document_id)

    def pending_ids(self, session: Session, limit: int) -> list[int]:
        return list(
            session.scalars(
                select(Document.id)
                .where(
                    Document.processing_status == "pending",
                    Document.archived_at.is_(None),
                )
                .order_by(Document.id.asc())
                .limit(limit)
            )
        )

    def stale_processing_ids(self, session: Session, cutoff: datetime, limit: int) -> list[int]:
        return list(
            session.scalars(
                select(Document.id)
                .where(
                    Document.processing_status == "processing",
                    Document.archived_at.is_(None),
                    Document.processing_started_at.is_not(None),
                    Document.processing_started_at < cutoff,
                )
                .order_by(Document.processing_started_at.asc(), Document.id.asc())
                .limit(limit)
            )
        )

    def replace_chunks(
        self,
        session: Session,
        document_id: int,
        chunks: tuple[PreparedChunk, ...],
        now: datetime,
    ) -> tuple[DocumentChunk, ...]:
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        entities = tuple(
            DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_title=chunk.section_title,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                created_at=now,
            )
            for chunk in chunks
        )
        session.add_all(entities)
        session.flush()
        return entities
