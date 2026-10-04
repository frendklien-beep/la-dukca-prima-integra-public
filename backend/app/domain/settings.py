from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EditableSettings:
    assistant_name: str
    ai_enabled: bool
    knowledge_base_enabled: bool


@dataclass(frozen=True, slots=True)
class ReadOnlySettings:
    source_required: bool
    web_search_enabled: bool
    chat_history_admin_enabled: bool
    system_prompt_version: str
    model_configuration_status: str


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    editable: EditableSettings
    read_only: ReadOnlySettings
