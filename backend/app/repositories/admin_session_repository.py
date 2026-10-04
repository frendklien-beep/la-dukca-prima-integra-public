from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.admin_session import AdminSession


class AdminSessionRepository:
    def get_by_token_hash(self, session: Session, token_hash: str) -> AdminSession | None:
        return session.scalar(
            select(AdminSession)
            .options(joinedload(AdminSession.admin))
            .where(AdminSession.token_hash == token_hash)
        )

    def list_active_for_admin(
        self, session: Session, admin_id: int, now: datetime
    ) -> list[AdminSession]:
        stmt = (
            select(AdminSession)
            .where(
                AdminSession.admin_id == admin_id,
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > now,
                AdminSession.idle_expires_at > now,
            )
            .order_by(AdminSession.last_seen_at.asc(), AdminSession.id.asc())
        )
        return list(session.scalars(stmt))

    def add(self, session: Session, value: AdminSession) -> AdminSession:
        session.add(value)
        session.flush()
        return value

    def revoke(self, value: AdminSession, now: datetime, reason: str) -> None:
        if value.revoked_at is None:
            value.revoked_at = now
            value.revoke_reason = reason

    def revoke_all_for_admin(
        self, session: Session, admin_id: int, now: datetime, reason: str
    ) -> int:
        values = self.list_active_for_admin(session, admin_id, now)
        for value in values:
            self.revoke(value, now, reason)
        return len(values)
