import json
import re
import unicodedata
from collections.abc import Mapping

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import SettingsInvalidError, SettingsNotInitializedError
from app.db.utc import utc_now
from app.domain.settings import EditableSettings, ReadOnlySettings, SettingsSnapshot
from app.models.app_setting import AppSetting
from app.repositories.app_setting_repository import AppSettingRepository
from app.repositories.audit_repository import AuditRepository

EDITABLE_KEYS = {"assistant_name", "ai_enabled", "knowledge_base_enabled"}
DEFAULT_TYPES = {
    "assistant_name": "string",
    "ai_enabled": "boolean",
    "knowledge_base_enabled": "boolean",
}
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
MARKUP_ONLY_PATTERN = re.compile(r"^[\s<>/\\\[\]{}()'\"`~!@#$%^&*_=+|:;,.?-]+$")


def normalize_assistant_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if CONTROL_PATTERN.search(normalized) or "\n" in normalized or "\r" in normalized:
        raise ValueError("Nama asisten tidak boleh memuat karakter kontrol atau baris baru.")
    normalized = " ".join(normalized.strip().split())
    if not 3 <= len(normalized) <= 80:
        raise ValueError("Nama asisten harus 3-80 karakter.")
    if MARKUP_ONLY_PATTERN.fullmatch(normalized):
        raise ValueError("Nama asisten harus memuat teks yang bermakna.")
    return normalized


class SettingsService:
    def __init__(self, repository=None, audits=None):
        self.repository = repository or AppSettingRepository()
        self.audits = audits or AuditRepository()

    @staticmethod
    def _defaults(settings: Settings) -> dict[str, object]:
        return {
            "assistant_name": normalize_assistant_name(settings.default_assistant_name),
            "ai_enabled": settings.default_ai_enabled,
            "knowledge_base_enabled": settings.default_knowledge_base_enabled,
        }

    def ensure_defaults(
        self,
        session: Session,
        *,
        settings: Settings,
        request_id: str | None = None,
    ) -> list[str]:
        defaults = self._defaults(settings)
        created: list[str] = []
        try:
            with session.begin():
                existing = {
                    row.key: row for row in self.repository.list_by_keys(session, set(defaults))
                }
                now = utc_now()
                for key, value in defaults.items():
                    if key in existing:
                        continue
                    self.repository.add(
                        session,
                        AppSetting(
                            key=key,
                            value_json=json.dumps(value, ensure_ascii=False),
                            value_type=DEFAULT_TYPES[key],
                            is_frontend_visible=True,
                            is_editable=True,
                            updated_by_admin_id=None,
                            created_at=now,
                            updated_at=now,
                        ),
                    )
                    created.append(key)
                if created:
                    self.audits.append_event(
                        session,
                        event_type="settings.bootstrap.created",
                        outcome="success",
                        request_id=request_id,
                        metadata={"created_keys": sorted(created)},
                    )
        except IntegrityError:
            session.rollback()
            return []
        return created

    def get_snapshot(self, session: Session, settings: Settings) -> SettingsSnapshot:
        rows = self.repository.list_by_keys(session, EDITABLE_KEYS)
        if {row.key for row in rows} != EDITABLE_KEYS:
            raise SettingsNotInitializedError()
        values: dict[str, object] = {}
        for row in rows:
            try:
                value = json.loads(row.value_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise SettingsInvalidError() from exc
            if row.value_type == "string" and not isinstance(value, str):
                raise SettingsInvalidError()
            if row.value_type == "boolean" and type(value) is not bool:
                raise SettingsInvalidError()
            values[row.key] = value
        editable = EditableSettings(
            assistant_name=normalize_assistant_name(str(values["assistant_name"])),
            ai_enabled=bool(values["ai_enabled"]),
            knowledge_base_enabled=bool(values["knowledge_base_enabled"]),
        )
        read_only = ReadOnlySettings(
            source_required=True,
            web_search_enabled=False,
            chat_history_admin_enabled=False,
            system_prompt_version=settings.system_prompt_version,
            model_configuration_status="configured" if settings.ai_configured else "unconfigured",
        )
        return SettingsSnapshot(editable=editable, read_only=read_only)

    def update(
        self,
        session: Session,
        *,
        submitted: Mapping[str, object],
        admin_id: int,
        request_id: str,
        settings: Settings,
    ) -> SettingsSnapshot:
        unknown = set(submitted) - EDITABLE_KEYS
        if unknown:
            raise ValueError(f"Pengaturan tidak diizinkan: {', '.join(sorted(unknown))}")
        if not submitted:
            raise ValueError("Minimal satu pengaturan harus dikirim.")
        normalized: dict[str, object] = {}
        for key, value in submitted.items():
            if value is None:
                raise ValueError("Nilai pengaturan tidak boleh null.")
            if key == "assistant_name":
                if not isinstance(value, str):
                    raise ValueError("assistant_name harus berupa teks.")
                normalized[key] = normalize_assistant_name(value)
            else:
                if type(value) is not bool:
                    raise ValueError(f"{key} harus boolean JSON.")
                normalized[key] = value

        with session.begin():
            rows = {row.key: row for row in self.repository.list_by_keys(session, EDITABLE_KEYS)}
            if set(rows) != EDITABLE_KEYS:
                raise SettingsNotInitializedError()
            changed: list[str] = []
            now = utc_now()
            for key, value in normalized.items():
                current = json.loads(rows[key].value_json)
                if current == value:
                    continue
                rows[key].value_json = json.dumps(value, ensure_ascii=False)
                rows[key].updated_by_admin_id = admin_id
                rows[key].updated_at = now
                changed.append(key)
            if changed:
                self.audits.append_event(
                    session,
                    event_type="settings.updated",
                    outcome="success",
                    request_id=request_id,
                    actor_admin_id=admin_id,
                    metadata={"changed_keys": sorted(changed)},
                )
        return self.get_snapshot(session, settings)


settings_service = SettingsService()
