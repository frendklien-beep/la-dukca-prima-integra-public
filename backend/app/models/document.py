from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size_bytes >= 0", name="file_size_nonnegative"),
        CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="page_count_nonnegative",
        ),
        CheckConstraint(
            "processing_status IN ('pending','processing','ready','failed','requires_ocr')",
            name="processing_status",
        ),
        Index("ix_documents_retrieval", "processing_status", "is_active", "archived_at"),
        Index(
            "ix_documents_processing_recovery",
            "processing_status",
            "processing_started_at",
            "archived_at",
        ),
        Index(
            "uq_documents_sha256_non_archived",
            "sha256_checksum",
            unique=True,
            sqlite_where=text("archived_at IS NULL"),
            postgresql_where=text("archived_at IS NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_char_count: Mapped[int | None] = mapped_column(Integer)
    processing_error_code: Mapped[str | None] = mapped_column(String(100))
    processing_error_message: Mapped[str | None] = mapped_column(String(500))
    uploaded_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    activated_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    authority_rank: Mapped[int | None] = mapped_column(Integer)
    document_number: Mapped[str | None] = mapped_column(String(120))
    document_year: Mapped[int | None] = mapped_column(Integer)
    issuer: Mapped[str | None] = mapped_column(String(255))
    jurisdiction: Mapped[str | None] = mapped_column(String(64))
    effective_date: Mapped[date | None]
    valid_until: Mapped[date | None]
    legal_status: Mapped[str | None] = mapped_column(String(32))
    document_type: Mapped[str | None] = mapped_column(String(64))
    amends_json: Mapped[str | None] = mapped_column(Text)
    amended_by_json: Mapped[str | None] = mapped_column(Text)
    revokes_json: Mapped[str | None] = mapped_column(Text)
    revoked_by_json: Mapped[str | None] = mapped_column(Text)
    topics_json: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    index_version: Mapped[str | None] = mapped_column(String(64))
    extraction_method: Mapped[str | None] = mapped_column(String(64))
    text_quality_score: Mapped[float | None]
    uploader = relationship("Admin", back_populates="uploaded_documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    message_sources = relationship("MessageSource", back_populates="document")
