from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import Admin


class AdminRepository:
    def get_by_normalized_username(self, session: Session, username: str) -> Admin | None:
        return session.scalar(select(Admin).where(Admin.username == username))

    def get_by_id(self, session: Session, admin_id: int) -> Admin | None:
        return session.get(Admin, admin_id)

    def add(self, session: Session, admin: Admin) -> Admin:
        session.add(admin)
        session.flush()
        return admin

    def reset_login_failure_state(self, admin: Admin) -> None:
        admin.failed_login_count = 0
        admin.failed_login_window_started_at = None
        admin.locked_until = None

    def set_password_hash(self, admin: Admin, password_hash: str) -> None:
        admin.password_hash = password_hash
