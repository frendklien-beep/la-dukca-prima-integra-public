from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app


def test_app_factory_instances_do_not_share_state(tmp_path: Path) -> None:
    first = create_app(
        Settings(environment=Environment.TESTING, data_dir=tmp_path / "a", build_id="first")
    )
    second = create_app(
        Settings(environment=Environment.TESTING, data_dir=tmp_path / "b", build_id="second")
    )
    assert first is not second
    assert first.state.settings.build_id == "first"
    assert second.state.settings.build_id == "second"
    first.state.engine.dispose()
    second.state.engine.dispose()


def test_production_disables_documentation(tmp_path: Path) -> None:
    app = create_app(Settings(environment=Environment.PRODUCTION, data_dir=tmp_path / "data"))
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_openapi_has_exact_application_paths(app) -> None:
    schema = app.openapi()
    assert set(schema["paths"]) == {
        "/health/live",
        "/health/ready",
        "/api/v1/system/version",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/csrf",
        "/api/v1/auth/logout",
        "/api/v1/admin/dashboard",
        "/api/v1/admin/settings",
        "/api/v1/admin/documents",
        "/api/v1/admin/documents/{document_id}",
        "/api/v1/admin/documents/{document_id}/activate",
        "/api/v1/admin/documents/{document_id}/deactivate",
        "/api/v1/admin/documents/{document_id}/archive",
        "/api/v1/admin/documents/{document_id}/retry",
        "/api/v1/chat",
        "/api/v1/chat/sessions/{session_id}/close",
    }


def test_openapi_operation_ids_are_exact_and_unique(app) -> None:
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
    ]
    assert set(operation_ids) == {
        "get_liveness",
        "get_readiness",
        "get_system_version",
        "admin_login",
        "get_current_admin",
        "refresh_admin_csrf",
        "admin_logout",
        "admin_get_dashboard",
        "admin_get_settings",
        "admin_update_settings",
        "admin_list_documents",
        "admin_upload_document",
        "admin_get_document",
        "admin_activate_document",
        "admin_deactivate_document",
        "admin_archive_document",
        "admin_retry_document",
        "publicChatSendMessage",
        "publicChatCloseSession",
    }
    assert len(operation_ids) == len(set(operation_ids))


def test_lifespan_sets_state_and_does_not_create_database(tmp_path: Path) -> None:
    data_dir = tmp_path / "runtime"
    app = create_app(Settings(environment=Environment.TESTING, data_dir=data_dir))
    with TestClient(app):
        assert app.state.started_at is not None
        assert app.state.storage_status == "ready"
    assert not list(data_dir.glob("*.db"))
    assert not list(data_dir.rglob(".readiness-*.tmp"))
