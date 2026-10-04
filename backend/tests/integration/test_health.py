from pathlib import Path

from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Environment, Settings
from app.db.migration_state import get_alembic_config
from app.main import create_app


def test_liveness_contract(client) -> None:
    response = client.get("/health/live")
    body = response.json()

    assert response.status_code == 200
    assert body["data"] == {
        "status": "alive",
        "service": "la-dukca-prima-integra-backend",
    }
    assert body["meta"]["timestamp"].endswith("Z")
    assert response.headers["x-request-id"] == body["meta"]["request_id"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_valid_request_id_header_is_preserved(client) -> None:
    request_id = "web-20260801-001"
    response = client.get("/health/live", headers={"X-Request-ID": request_id})
    assert response.headers["x-request-id"] == request_id
    assert response.json()["meta"]["request_id"] == request_id


def test_invalid_request_id_header_is_replaced(client) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "invalid request"})
    assert response.headers["x-request-id"] != "invalid request"


def test_readiness_bootstrap_contract(client) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ready",
        "components": {
            "database": "ready",
            "storage": "ready",
            "migrations": "ready",
            "knowledge_base": "empty",
            "ai_configuration": "unconfigured",
        },
    }


def test_readiness_reports_configured_api_key(tmp_path: Path) -> None:
    settings = Settings(
        environment=Environment.TESTING,
        data_dir=tmp_path / "data",
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'configured.db').as_posix()}",
        openai_api_key="test-key-not-real",
    )
    command.upgrade(get_alembic_config(settings.project_dir, settings.database_url), "head")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["data"]["components"]["ai_configuration"] == "configured"


def test_storage_failure_returns_safe_503(tmp_path: Path) -> None:
    invalid_data_dir = tmp_path / "not-a-directory"
    invalid_data_dir.write_text("file blocks directory creation", encoding="utf-8")
    settings = Settings(environment=Environment.TESTING, data_dir=invalid_data_dir)

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/health/ready")

    body = response.json()
    assert response.status_code == 503
    assert body["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert body["error"]["retryable"] is True
    assert str(tmp_path) not in response.text
    assert response.headers["x-request-id"] == body["error"]["request_id"]


def test_probe_files_are_cleaned_up(client, test_settings: Settings) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert not list(test_settings.data_dir.rglob(".readiness-*.tmp"))
