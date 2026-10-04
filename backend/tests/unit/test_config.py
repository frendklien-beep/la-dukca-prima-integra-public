from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings, get_settings


def test_default_settings_are_valid() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "La Dukca PRIMA Integra"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.docs_enabled is True


def test_testing_environment_is_accepted(tmp_path: Path) -> None:
    settings = Settings(environment="testing", data_dir=tmp_path)
    assert settings.environment is Environment.TESTING


def test_demo_debug_true_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="demo", debug=True)


def test_production_docs_are_disabled() -> None:
    settings = Settings(environment="production")
    assert settings.docs_enabled is False


def test_prefix_requires_leading_slash() -> None:
    with pytest.raises(ValidationError):
        Settings(api_v1_prefix="api/v1")


def test_prefix_rejects_trailing_slash() -> None:
    with pytest.raises(ValidationError):
        Settings(api_v1_prefix="/api/v1/")


def test_port_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(port=70000)


def test_public_metadata_excludes_secret() -> None:
    settings = Settings(openai_api_key="sensitive-test-key")
    public = settings.public_metadata()
    assert "openai_api_key" not in public
    assert "sensitive-test-key" not in str(public)


def test_derived_paths(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime")
    assert settings.uploads_dir == tmp_path / "runtime" / "uploads"
    assert settings.processed_dir == tmp_path / "runtime" / "processed"
    assert settings.indexes_dir == tmp_path / "runtime" / "indexes"


def test_get_settings_cache_can_be_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_VERSION", "1.0.0")
    first = get_settings()
    monkeypatch.setenv("APP_VERSION", "2.0.0")
    assert get_settings().app_version == first.app_version
    get_settings.cache_clear()
    assert get_settings().app_version == "2.0.0"
    get_settings.cache_clear()


def test_sprint5_conversation_defaults() -> None:
    from app.core.config import Settings

    settings = Settings()
    assert settings.app_version == "0.5.0"
    assert settings.system_prompt_version == "la-dukca-system-v2"
    assert settings.conversation_max_intents == 5
    assert settings.public_chat_rate_limit_per_minute == 10
    assert settings.public_chat_rate_limit_burst == 3
    assert settings.retrieval_candidate_top_k == 12
    assert settings.retrieval_final_top_k == 5
    assert settings.openai_max_output_tokens == 1200
