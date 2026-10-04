import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import DUMMY_HASH, digest_token, normalize_username, verify_password
from app.models.admin import Admin
from app.models.admin_session import AdminSession
from app.repositories.admin_repository import AdminRepository
from app.repositories.admin_session_repository import AdminSessionRepository
from app.repositories.audit_repository import AuditRepository


@dataclass(frozen=True)
class LoginResult:
    status: str
    admin: Admin | None = None
    session: AdminSession | None = None
    raw_session_token: str | None = None
    raw_csrf_token: str | None = None


class AuthenticationService:
    def __init__(self, admins=None, sessions=None, audits=None):
        self.admins = admins or AdminRepository()
        self.sessions = sessions or AdminSessionRepository()
        self.audits = audits or AuditRepository()

    def login(
        self,
        db: Session,
        *,
        username: str,
        password: str,
        remember_me: bool,
        request_id: str,
        settings: Settings,
        clock: Clock,
    ) -> LoginResult:
        now = clock.now()
        normalized = normalize_username(username)
        with db.begin():
            admin = self.admins.get_by_normalized_username(db, normalized)
            valid, updated_hash = verify_password(
                password, admin.password_hash if admin else DUMMY_HASH
            )
            if admin is None:
                self.audits.append_event(
                    db,
                    event_type="admin.login.failure",
                    outcome="failure",
                    request_id=request_id,
                    metadata={"reason_code": "invalid_credentials"},
                )
                return LoginResult("invalid")

            locked = admin.locked_until is not None and admin.locked_until > now
            if not valid or not admin.is_active or locked:
                if not locked:
                    window = settings.admin_login_failure_window_minutes
                    if (
                        admin.failed_login_window_started_at is None
                        or admin.failed_login_window_started_at < now - timedelta(minutes=window)
                    ):
                        admin.failed_login_count = 1
                        admin.failed_login_window_started_at = now
                    else:
                        admin.failed_login_count += 1
                    if admin.failed_login_count >= settings.admin_login_max_failures:
                        admin.locked_until = now + timedelta(
                            minutes=settings.admin_login_lock_minutes
                        )
                    admin.updated_at = now
                self.audits.append_event(
                    db,
                    event_type="admin.login.blocked" if locked else "admin.login.failure",
                    outcome="blocked" if locked else "failure",
                    request_id=request_id,
                    metadata={"reason_code": "invalid_credentials"},
                )
                return LoginResult("invalid")

            raw_session = secrets.token_urlsafe(32)
            raw_csrf = secrets.token_urlsafe(32)
            if remember_me:
                idle = now + timedelta(hours=settings.admin_remember_idle_hours)
                absolute = now + timedelta(days=settings.admin_remember_absolute_days)
            else:
                idle = now + timedelta(minutes=settings.admin_session_idle_minutes)
                absolute = now + timedelta(hours=settings.admin_session_absolute_hours)

            new_session = AdminSession(
                admin_id=admin.id,
                token_hash=digest_token(raw_session),
                csrf_token_hash=digest_token(raw_csrf),
                remember_me=remember_me,
                created_at=now,
                last_seen_at=now,
                expires_at=absolute,
                idle_expires_at=min(idle, absolute),
                revoked_at=None,
                revoke_reason=None,
                created_user_agent_hash=None,
            )
            self.admins.reset_login_failure_state(admin)
            admin.last_login_at = now
            admin.updated_at = now
            if updated_hash:
                admin.password_hash = updated_hash

            active = self.sessions.list_active_for_admin(db, admin.id, now)
            overflow = max(0, len(active) + 1 - settings.admin_max_active_sessions)
            for old in active[:overflow]:
                self.sessions.revoke(old, now, "session_limit")
                self.audits.append_event(
                    db,
                    event_type="admin.session.revoked",
                    outcome="success",
                    request_id=request_id,
                    actor_admin_id=admin.id,
                    metadata={"session_id": old.id, "reason_code": "session_limit"},
                )
            self.sessions.add(db, new_session)
            self.audits.append_event(
                db,
                event_type="admin.login.success",
                outcome="success",
                request_id=request_id,
                actor_admin_id=admin.id,
                metadata={
                    "remember_me": remember_me,
                    "session_id": new_session.id,
                    "password_hash_rehashed": bool(updated_hash),
                },
            )
            return LoginResult("success", admin, new_session, raw_session, raw_csrf)


authentication_service = AuthenticationService()
