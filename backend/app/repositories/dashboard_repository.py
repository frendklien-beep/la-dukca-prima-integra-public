from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.document import Document


@dataclass(frozen=True, slots=True)
class DocumentCounts:
    total: int
    active: int
    processing: int
    failed: int
    requires_ocr: int


class DashboardRepository:
    def get_counts(self, session: Session) -> DocumentCounts:
        row = session.execute(
            select(
                func.count(Document.id),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (Document.processing_status == "ready")
                                & (Document.is_active.is_(True)),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (Document.processing_status.in_(["pending", "processing"]), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Document.processing_status == "failed", 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Document.processing_status == "requires_ocr", 1), else_=0)),
                    0,
                ),
            ).where(Document.archived_at.is_(None))
        ).one()
        return DocumentCounts(*(int(value or 0) for value in row))

    def get_latest_non_archived(self, session: Session) -> Document | None:
        return session.scalar(
            select(Document)
            .where(Document.archived_at.is_(None))
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(1)
        )
