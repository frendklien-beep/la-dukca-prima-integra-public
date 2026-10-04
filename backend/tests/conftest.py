from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

try:
    __import__("pwdlib")
except ImportError:  # container-only verification fallback
    from argon2 import PasswordHasher

    class _PasswordHash:
        def __init__(self) -> None:
            self._hasher = PasswordHasher()

        @classmethod
        def recommended(cls):
            return cls()

        def hash(self, password: str) -> str:
            return self._hasher.hash(password)

        def verify_and_update(self, password: str, encoded: str):
            try:
                valid = self._hasher.verify(encoded, password)
                updated = (
                    self._hasher.hash(password)
                    if self._hasher.check_needs_rehash(encoded)
                    else None
                )
                return valid, updated
            except Exception:
                return False, None

    module = types.ModuleType("pwdlib")
    module.PasswordHash = _PasswordHash
    sys.modules["pwdlib"] = module

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Environment, Settings
from app.core.security import hash_password
from app.db.migration_state import get_alembic_config
from app.main import create_app
from app.models.admin import Admin

PASSWORD = "Correct Horse Battery 123"
FIXED_NOW = datetime(2026, 8, 1, 2, 30, tzinfo=UTC)


class FixedClock:
    def __init__(self, value: datetime = FIXED_NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "test.db"
    settings = Settings(
        environment=Environment.TESTING,
        debug=False,
        data_dir=tmp_path / "data",
        database_url=f"sqlite+pysqlite:///{database_path.as_posix()}",
        build_id="test-build",
        openai_api_key=None,
        allowed_origins=["http://localhost:5173"],
    )
    config = get_alembic_config(settings.project_dir, settings.database_url)
    command.upgrade(config, "head")
    return settings


@pytest.fixture
def app(test_settings: Settings) -> Iterator[FastAPI]:
    application = create_app(test_settings)
    application.state.clock = FixedClock()
    try:
        yield application
    finally:
        application.state.engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def active_admin(app: FastAPI) -> Admin:
    now = app.state.clock.now()
    with app.state.session_factory() as db:
        with db.begin():
            admin = Admin(
                username="administrator",
                password_hash=hash_password(PASSWORD),
                display_name="Administrator",
                email=None,
                role="administrator",
                is_active=True,
                failed_login_count=0,
                failed_login_window_started_at=None,
                locked_until=None,
                last_login_at=None,
                password_changed_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(admin)
        db.refresh(admin)
        db.expunge(admin)
        return admin


@pytest.fixture
def authenticated_client(client: TestClient, active_admin: Admin) -> tuple[TestClient, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "administrator", "password": PASSWORD, "remember_me": False},
    )
    assert response.status_code == 200
    return client, response.json()["data"]["csrf_token"]


@pytest.fixture
def mutation_headers(authenticated_client: tuple[TestClient, str]) -> dict[str, str]:
    _client, csrf_token = authenticated_client
    return {
        "Origin": "http://localhost:5173",
        "X-CSRF-Token": csrf_token,
    }


@pytest.fixture
def valid_pdf_bytes() -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Dokumen resmi La Dukca PRIMA Integra")
    payload = document.tobytes()
    document.close()
    return payload
