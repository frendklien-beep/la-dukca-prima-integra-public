from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting


class AppSettingRepository:
    def list_by_keys(self, session: Session, keys: set[str]) -> list[AppSetting]:
        return list(session.scalars(select(AppSetting).where(AppSetting.key.in_(keys))))

    def get_by_key(self, session: Session, key: str) -> AppSetting | None:
        return session.scalar(select(AppSetting).where(AppSetting.key == key))

    def add(self, session: Session, setting: AppSetting) -> AppSetting:
        session.add(setting)
        session.flush()
        return setting
