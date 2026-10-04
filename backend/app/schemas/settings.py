from pydantic import BaseModel, ConfigDict, StrictBool, field_validator, model_validator

from app.schemas.common import SuccessEnvelope
from app.services.settings_service import normalize_assistant_name


class EditableSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assistant_name: str
    ai_enabled: bool
    knowledge_base_enabled: bool


class ReadOnlySettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_required: bool
    web_search_enabled: bool
    chat_history_admin_enabled: bool
    system_prompt_version: str
    model_configuration_status: str


class AdminSettingsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    editable: EditableSettingsSchema
    read_only: ReadOnlySettingsSchema


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assistant_name: str | None = None
    ai_enabled: StrictBool | None = None
    knowledge_base_enabled: StrictBool | None = None

    @field_validator("assistant_name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_assistant_name(value)

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("Minimal satu pengaturan harus dikirim.")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError("Nilai pengaturan tidak boleh null.")
        return self


AdminSettingsResponse = SuccessEnvelope[AdminSettingsData]
