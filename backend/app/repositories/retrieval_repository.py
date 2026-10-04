from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.conversation.regulatory import parse_relationships


@dataclass(frozen=True, slots=True)
class RetrievalChunkRecord:
    id: int
    document_id: int
    content: str
    content_hash: str
    page_start: int | None
    page_end: int | None
    section_title: str | None
    token_count: int


@dataclass(frozen=True, slots=True)
class RetrievalDocumentRecord:
    id: int
    title: str
    category: str
    authority_rank: int
    jurisdiction: str
    effective_date: date | None
    index_version: str
    document_number: str | None
    legal_status: str | None
    chunks: tuple[RetrievalChunkRecord, ...]
    document_year: int | None = None
    issuer: str | None = None
    document_type: str | None = None
    amends: tuple[str, ...] = ()
    amended_by: tuple[str, ...] = ()
    revokes: tuple[str, ...] = ()
    revoked_by: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()


class RetrievalRepository:
    def eligible_documents(self, session: Session) -> tuple[RetrievalDocumentRecord, ...]:
        documents = tuple(
            session.scalars(
                select(Document)
                .where(
                    Document.processing_status == "ready",
                    Document.is_active.is_(True),
                    Document.archived_at.is_(None),
                    Document.index_version.is_not(None),
                    or_(
                        Document.legal_status != "revoked",
                        Document.legal_status.is_(None),
                    ),
                )
                .order_by(Document.id.asc())
            )
        )
        if not documents:
            return ()
        ids = [document.id for document in documents]
        chunk_rows = tuple(
            session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id.in_(ids))
                .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
            )
        )
        by_document: dict[int, list[RetrievalChunkRecord]] = {value: [] for value in ids}
        for chunk in chunk_rows:
            by_document[chunk.document_id].append(
                RetrievalChunkRecord(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                    token_count=chunk.token_count or 0,
                )
            )
        return tuple(
            RetrievalDocumentRecord(
                id=document.id,
                title=document.title,
                category=document.category,
                authority_rank=document.authority_rank or 0,
                jurisdiction=document.jurisdiction or "unknown",
                effective_date=document.effective_date,
                index_version=str(document.index_version),
                document_number=document.document_number,
                legal_status=document.legal_status,
                chunks=tuple(by_document[document.id]),
                document_year=document.document_year,
                issuer=document.issuer,
                document_type=document.document_type or document.category,
                amends=parse_relationships(document.amends_json),
                amended_by=parse_relationships(document.amended_by_json),
                revokes=parse_relationships(document.revokes_json),
                revoked_by=parse_relationships(document.revoked_by_json),
                topics=parse_relationships(document.topics_json),
            )
            for document in documents
        )
