from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import SuccessEnvelope


class DocumentProcessingErrorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class DocumentListItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    title: str
    original_filename: str
    category: str
    category_code: str
    file_size_bytes: int
    processing_status: str
    display_status: str
    is_active: bool
    is_archived: bool
    retrieval_eligible: bool
    page_count: int | None
    created_at: datetime
    updated_at: datetime


class DocumentDetailSchema(DocumentListItemSchema):
    description: str | None
    mime_type: str
    extracted_char_count: int | None
    chunk_count: int
    processing_error: DocumentProcessingErrorSchema | None
    uploaded_by: str | None
    processed_at: datetime | None
    activated_at: datetime | None
    archived_at: datetime | None
    poll_after_seconds: int | None


class PaginationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class DocumentListData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[DocumentListItemSchema]
    pagination: PaginationSchema


class DocumentUploadData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: DocumentDetailSchema
    poll_after_seconds: int = 2


class DocumentActionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: DocumentDetailSchema


class DocumentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = Field(default=None, max_length=100)
    category: str | None = None
    processing_status: str | None = None
    is_active: bool | None = None
    include_archived: bool = False
    sort_by: str = "created_at"
    sort_order: str = "desc"


DocumentListResponse = SuccessEnvelope[DocumentListData]
DocumentUploadResponse = SuccessEnvelope[DocumentUploadData]
DocumentDetailResponse = SuccessEnvelope[DocumentDetailSchema]
DocumentActionResponse = SuccessEnvelope[DocumentActionData]
