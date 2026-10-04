from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime


class MessageSource(Base):
    __tablename__ = "message_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("public_chat_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_snapshot: Mapped[str | None] = mapped_column(String(255))
    relevance_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    message = relationship("PublicChatMessage", back_populates="sources")
    document = relationship("Document", back_populates="message_sources")
    chunk = relationship("DocumentChunk", back_populates="message_sources")
