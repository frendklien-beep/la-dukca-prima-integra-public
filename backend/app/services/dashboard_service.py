from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.dashboard import (
    AIDashboardStatus,
    DashboardSnapshot,
    KnowledgeBaseDashboardStatus,
    LastUploadSummary,
    SystemDashboardStatus,
)
from app.repositories.dashboard_repository import DashboardRepository
from app.services.documents.document_types import display_status
from app.services.settings_service import SettingsService


class DashboardService:
    def __init__(self, repository=None, settings_service=None):
        self.repository = repository or DashboardRepository()
        self.settings_service = settings_service or SettingsService()

    def get_snapshot(
        self,
        *,
        session: Session,
        settings: Settings,
        storage_status: str,
    ) -> DashboardSnapshot:
        settings_snapshot = self.settings_service.get_snapshot(session, settings)
        counts = self.repository.get_counts(session)
        kb_enabled = settings_snapshot.editable.knowledge_base_enabled
        kb_status = (
            "empty"
            if counts.total == 0
            else "ready"
            if kb_enabled and counts.active > 0
            else "degraded"
        )
        configured = settings.ai_configured
        if not settings_snapshot.editable.ai_enabled:
            ai_status = "disabled"
        elif not configured:
            ai_status = "unconfigured"
        elif not kb_enabled or counts.active == 0:
            ai_status = "waiting_for_knowledge"
        else:
            ai_status = "ready"
        overall = (
            "ready"
            if storage_status == "ready" and ai_status == "ready" and kb_status == "ready"
            else "degraded"
        )
        latest = self.repository.get_latest_non_archived(session)
        last_upload = None
        if latest is not None:
            last_upload = LastUploadSummary(
                document_id=latest.id,
                title=latest.title,
                display_status=display_status(latest),
                created_at=latest.created_at,
            )
        return DashboardSnapshot(
            system=SystemDashboardStatus(
                overall_status=overall,
                backend="ready",
                database="ready",
                storage="ready" if storage_status == "ready" else "unavailable",
            ),
            ai=AIDashboardStatus(
                enabled=settings_snapshot.editable.ai_enabled,
                configured=configured,
                status=ai_status,
            ),
            knowledge_base=KnowledgeBaseDashboardStatus(
                status=kb_status,
                total_documents=counts.total,
                active_documents=counts.active,
                processing_documents=counts.processing,
                failed_documents=counts.failed,
                requires_ocr_documents=counts.requires_ocr,
            ),
            last_upload=last_upload,
        )


dashboard_service = DashboardService()
