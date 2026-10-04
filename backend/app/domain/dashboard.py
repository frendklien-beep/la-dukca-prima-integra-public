from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SystemDashboardStatus:
    overall_status: str
    backend: str
    database: str
    storage: str


@dataclass(frozen=True, slots=True)
class AIDashboardStatus:
    enabled: bool
    configured: bool
    status: str


@dataclass(frozen=True, slots=True)
class KnowledgeBaseDashboardStatus:
    status: str
    total_documents: int
    active_documents: int
    processing_documents: int
    failed_documents: int
    requires_ocr_documents: int


@dataclass(frozen=True, slots=True)
class LastUploadSummary:
    document_id: int
    title: str
    display_status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    system: SystemDashboardStatus
    ai: AIDashboardStatus
    knowledge_base: KnowledgeBaseDashboardStatus
    last_upload: LastUploadSummary | None
