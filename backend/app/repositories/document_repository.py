from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.admin import Admin
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    document: Document
    chunk_count: int
    uploader_display_name: str | None


class DocumentRepository:
    @staticmethod
    def _record_query() -> Select:
        chunk_count = (
            select(func.count(DocumentChunk.id))
            .where(DocumentChunk.document_id == Document.id)
            .correlate(Document)
            .scalar_subquery()
        )
        return select(Document, chunk_count.label("chunk_count"), Admin.display_name).outerjoin(
            Admin, Admin.id == Document.uploaded_by_admin_id
        )

    def add(self, session: Session, document: Document) -> Document:
        session.add(document)
        session.flush()
        return document

    def get_by_id(self, session: Session, document_id: int) -> DocumentRecord | None:
        row = session.execute(self._record_query().where(Document.id == document_id)).one_or_none()
        if row is None:
            return None
        return DocumentRecord(row[0], int(row[1] or 0), row[2])

    def get_entity(self, session: Session, document_id: int) -> Document | None:
        return session.get(Document, document_id)

    def get_by_checksum_non_archived(self, session: Session, checksum: str) -> Document | None:
        return session.scalar(
            select(Document).where(
                Document.sha256_checksum == checksum,
                Document.archived_at.is_(None),
            )
        )

    def list_paginated(
        self,
        session: Session,
        *,
        page: int,
        page_size: int,
        search: str | None,
        category: str | None,
        processing_status: str | None,
        is_active: bool | None,
        include_archived: bool,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[DocumentRecord], int]:
        filters = []
        if not include_archived:
            filters.append(Document.archived_at.is_(None))
        if category:
            filters.append(Document.category == category)
        if processing_status:
            filters.append(Document.processing_status == processing_status)
        if is_active is not None:
            filters.append(Document.is_active.is_(is_active))
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped.casefold()}%"
            filters.append(
                or_(
                    func.lower(Document.title).like(pattern, escape="\\"),
                    func.lower(Document.original_filename).like(pattern, escape="\\"),
                    func.lower(func.coalesce(Document.description, "")).like(pattern, escape="\\"),
                )
            )
        sort_columns = {
            "created_at": Document.created_at,
            "updated_at": Document.updated_at,
            "title": Document.title,
            "category": Document.category,
            "processing_status": Document.processing_status,
        }
        column = sort_columns[sort_by]
        order = column.asc() if sort_order == "asc" else column.desc()
        id_order = Document.id.asc() if sort_order == "asc" else Document.id.desc()
        total = int(session.scalar(select(func.count(Document.id)).where(*filters)) or 0)
        rows = session.execute(
            self._record_query()
            .where(*filters)
            .order_by(order, id_order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [DocumentRecord(row[0], int(row[1] or 0), row[2]) for row in rows], total
