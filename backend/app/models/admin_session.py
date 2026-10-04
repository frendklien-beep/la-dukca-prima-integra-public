from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.admin import Admin


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
        CheckConstraint("expires_at > created_at", name="absolute_expiry"),
        CheckConstraint("idle_expires_at > created_at", name="idle_expiry"),
        Index("ix_admin_sessions_admin_active", "admin_id", "revoked_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    remember_me: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    idle_expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), index=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(100))
    created_user_agent_hash: Mapped[str | None] = mapped_column(String(64))

    admin: Mapped[Admin] = relationship(back_populates="sessions")
