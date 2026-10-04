from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SafeProcessingError:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DocumentView:
    id: int
    title: str
    original_filename: str
    category: str
    category_code: str
    description: str | None
    mime_type: str
    file_size_bytes: int
    processing_status: str
    display_status: str
    is_active: bool
    is_archived: bool
    retrieval_eligible: bool
    page_count: int | None
    extracted_char_count: int | None
    chunk_count: int
    processing_error: SafeProcessingError | None
    uploaded_by: str | None
    processed_at: datetime | None
    activated_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    poll_after_seconds: int | None


@dataclass(frozen=True, slots=True)
class DocumentPage:
    items: list[DocumentView]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool
