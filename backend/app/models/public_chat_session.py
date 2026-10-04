from datetime import datetime

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime


class PublicChatSession(Base):
    __tablename__ = "public_chat_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active','closed','expired')", name="status"),
        CheckConstraint("message_count >= 0", name="message_count_nonnegative"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    message_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    greeting_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    messages = relationship(
        "PublicChatMessage", back_populates="session", cascade="all, delete-orphan"
    )
