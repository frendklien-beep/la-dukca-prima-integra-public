import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import digest_token
from app.models.admin import Admin
from app.models.admin_session import AdminSession
from app.repositories.admin_session_repository import AdminSessionRepository
from app.repositories.audit_repository import AuditRepository


@dataclass(frozen=True)
class AuthContext:
    admin: Admin
    session: AdminSession


class AdminSessionService:
    def __init__(self, sessions=None, audits=None):
        self.sessions = sessions or AdminSessionRepository()
        self.audits = audits or AuditRepository()

    def resolve(
        self,
        db: Session,
        raw_token: str,
        clock: Clock,
        settings: Settings,
    ) -> AuthContext | None:
        now = clock.now()
        value = self.sessions.get_by_token_hash(db, digest_token(raw_token))
        if (
            value is None
            or value.revoked_at is not None
            or value.expires_at <= now
            or value.idle_expires_at <= now
            or not value.admin.is_active
        ):
            return None
        if now - value.last_seen_at >= timedelta(minutes=settings.admin_last_seen_write_minutes):
            value.last_seen_at = now
            duration = (
                timedelta(hours=settings.admin_remember_idle_hours)
                if value.remember_me
                else timedelta(minutes=settings.admin_session_idle_minutes)
            )
            value.idle_expires_at = min(now + duration, value.expires_at)
            db.commit()
        return AuthContext(value.admin, value)

    def rotate_csrf(self, db: Session, context: AuthContext) -> str:
        raw = secrets.token_urlsafe(32)
        context.session.csrf_token_hash = digest_token(raw)
        db.commit()
        return raw

    def logout(
        self,
        db: Session,
        context: AuthContext,
        request_id: str,
        clock: Clock,
    ) -> None:
        now = clock.now()
        self.sessions.revoke(context.session, now, "logout")
        self.audits.append_event(
            db,
            event_type="admin.logout",
            outcome="success",
            request_id=request_id,
            actor_admin_id=context.admin.id,
            metadata={"session_id": context.session.id},
        )
        db.commit()


admin_session_service = AdminSessionService()
