import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEMO = "demo"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="La Dukca PRIMA Integra", min_length=1, max_length=100)
    service_name: str = Field(
        default="la-dukca-prima-integra-backend",
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    app_version: str = "0.5.0"
    api_v1_prefix: str = "/api/v1"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    build_id: str = "local"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Path("data")

    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-5-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    system_prompt_version: str = "la-dukca-system-v2"

    database_url: str = "sqlite+pysqlite:///./data/la_dukca.db"
    database_echo: bool = False
    database_busy_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    sqlite_wal_enabled: bool = True

    admin_session_cookie_name: str = "la_dukca_admin_session"
    admin_session_idle_minutes: int = 120
    admin_session_absolute_hours: int = 8
    admin_remember_idle_hours: int = 24
    admin_remember_absolute_days: int = 7
    admin_max_active_sessions: int = 3
    admin_last_seen_write_minutes: int = 5
    admin_login_max_failures: int = 5
    admin_login_failure_window_minutes: int = 15
    admin_login_lock_minutes: int = 15
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 60

    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    allowed_origins: list[str] = ["http://localhost:5173"]

    document_max_size_bytes: int = Field(default=104857600, ge=1)
    document_max_pages: int = Field(default=500, ge=1, le=5000)
    document_stream_chunk_bytes: int = Field(default=1048576, ge=4096)
    document_temp_retention_hours: int = Field(default=24, ge=1, le=720)

    processing_queue_max_size: int = Field(default=20, ge=1, le=1000)
    processing_worker_count: int = Field(default=1, ge=1, le=1)
    processing_job_timeout_seconds: int = Field(default=300, ge=10, le=3600)
    processing_recovery_batch_size: int = Field(default=50, ge=1, le=1000)
    processing_stale_after_minutes: int = Field(default=15, ge=1, le=1440)

    pdf_min_total_extracted_chars: int = Field(default=200, ge=1)
    pdf_min_page_text_chars: int = Field(default=40, ge=1)
    pdf_max_low_text_page_ratio: float = Field(default=0.50, ge=0.0, le=1.0)
    pdf_min_pages_with_text_ratio: float = Field(default=0.50, ge=0.0, le=1.0)
    pdf_max_replacement_character_ratio: float = Field(default=0.02, ge=0.0, le=1.0)
    pdf_min_alphabetic_ratio: float = Field(default=0.20, ge=0.0, le=1.0)

    chunk_target_tokens: int = Field(default=500, ge=32)
    chunk_max_tokens: int = Field(default=650, ge=64)
    chunk_min_tokens: int = Field(default=120, ge=1)
    chunk_overlap_tokens: int = Field(default=80, ge=0)

    embedding_batch_size: int = Field(default=64, ge=1, le=2048)
    embedding_timeout_seconds: int = Field(default=60, ge=1, le=600)
    embedding_max_attempts: int = Field(default=3, ge=1, le=10)
    knowledge_pipeline_version: str = "kb-v1"
    index_schema_version: str = "1"

    public_chat_session_hours: int = Field(default=24, ge=1, le=168)
    public_chat_context_messages: int = Field(default=12, ge=2, le=50)
    public_chat_rate_limit_per_minute: int = Field(default=10, ge=1, le=600)
    public_chat_rate_limit_burst: int = Field(default=3, ge=1, le=100)
    conversation_max_intents: int = Field(default=5, ge=1, le=5)
    retrieval_candidate_top_k: int = Field(default=12, ge=1, le=100)
    retrieval_final_top_k: int = Field(default=5, ge=1, le=20)
    retrieval_max_chunks_per_document: int = Field(default=2, ge=1, le=10)
    retrieval_max_documents: int = Field(default=4, ge=1, le=20)
    retrieval_min_cosine_score: float = Field(default=0.45, ge=-1.0, le=1.0)
    retrieval_exact_match_min_score: float = Field(default=0.40, ge=-1.0, le=1.0)
    retrieval_context_max_tokens: int = Field(default=4500, ge=256, le=20000)
    retrieval_context_per_intent_tokens: int = Field(default=1800, ge=128, le=10000)
    openai_history_max_messages: int = Field(default=6, ge=0, le=20)
    openai_history_max_tokens: int = Field(default=1200, ge=0, le=10000)
    openai_max_output_tokens: int = Field(default=1200, ge=128, le=10000)
    openai_generation_timeout_seconds: int = Field(default=30, ge=1, le=300)
    openai_generation_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_diagnostic_logging: bool = False

    default_assistant_name: str = "Asisten La Dukca"
    default_ai_enabled: bool = True
    default_knowledge_base_enabled: bool = True

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str]:
        if not value or "*" in value or "null" in value:
            raise ValueError("ALLOWED_ORIGINS harus exact dan tidak boleh wildcard/null.")
        return list(dict.fromkeys(value))

    @field_validator("cookie_samesite")
    @classmethod
    def same_site(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE tidak valid.")
        return normalized

    @field_validator("api_v1_prefix")
    @classmethod
    def prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/") or (normalized != "/" and normalized.endswith("/")):
            raise ValueError("API_V1_PREFIX tidak valid.")
        return normalized

    @field_validator("log_level")
    @classmethod
    def log(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("LOG_LEVEL tidak valid.")
        return normalized

    @field_validator("openai_chat_model", "openai_embedding_model", "system_prompt_version")
    @classmethod
    def non_empty_model_config(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Konfigurasi model/prompt tidak boleh kosong.")
        return normalized

    @model_validator(mode="after")
    def validate_environment(self) -> Self:
        if self.environment is not Environment.DEVELOPMENT and self.debug:
            raise ValueError("DEBUG hanya boleh aktif pada development.")
        if self.cookie_secure and not self.admin_session_cookie_name.startswith("__Host-"):
            self.admin_session_cookie_name = "__Host-la_dukca_admin_session"
        if not self.cookie_secure and self.admin_session_cookie_name.startswith("__Host-"):
            raise ValueError("Cookie __Host- membutuhkan HTTPS/Secure.")
        if self.chunk_min_tokens > self.chunk_target_tokens:
            raise ValueError("CHUNK_MIN_TOKENS tidak boleh melebihi CHUNK_TARGET_TOKENS.")
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("CHUNK_TARGET_TOKENS tidak boleh melebihi CHUNK_MAX_TOKENS.")
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS harus lebih kecil dari CHUNK_MAX_TOKENS.")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.environment is not Environment.PRODUCTION

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def indexes_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def ai_configured(self) -> bool:
        key_ready = self.openai_api_key is not None and bool(
            self.openai_api_key.get_secret_value().strip()
        )
        return key_ready and bool(self.openai_chat_model) and bool(self.openai_embedding_model)

    @property
    def project_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def public_metadata(self) -> dict[str, str]:
        return {
            "app_name": self.app_name,
            "service_name": self.service_name,
            "app_version": self.app_version,
            "api_v1_prefix": self.api_v1_prefix,
            "environment": self.environment.value,
            "build_id": self.build_id,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
