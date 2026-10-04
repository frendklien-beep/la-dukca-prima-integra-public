from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import SuccessEnvelope


class SystemDashboardSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_status: str
    backend: str
    database: str
    storage: str


class AIDashboardSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    configured: bool
    status: str


class KnowledgeBaseDashboardSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    total_documents: int
    active_documents: int
    processing_documents: int
    failed_documents: int
    requires_ocr_documents: int


class LastUploadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: int
    title: str
    display_status: str
    created_at: datetime


class DashboardData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: SystemDashboardSchema
    ai: AIDashboardSchema
    knowledge_base: KnowledgeBaseDashboardSchema
    last_upload: LastUploadSchema | None


DashboardResponse = SuccessEnvelope[DashboardData]
