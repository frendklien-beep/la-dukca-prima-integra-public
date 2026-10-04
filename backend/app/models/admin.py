from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.admin_session import AdminSession


class Admin(Base):
    __tablename__ = "admins"
    __table_args__ = (
        UniqueConstraint("username", name="uq_admins_username"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_nonnegative"),
        CheckConstraint("role IN ('administrator')", name="role"),
        Index("ix_admins_locked_until", "locked_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="administrator")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_login_window_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    password_changed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    sessions: Mapped[list[AdminSession]] = relationship(back_populates="admin")
    uploaded_documents = relationship("Document", back_populates="uploader")
    updated_settings = relationship("AppSetting", back_populates="updated_by")
    audit_events = relationship("AuditEvent", back_populates="actor_admin")
