from dataclasses import asdict

from app.domain.dashboard import DashboardSnapshot
from app.domain.documents import DocumentPage, DocumentView
from app.domain.settings import SettingsSnapshot
from app.schemas.dashboard import (
    AIDashboardSchema,
    DashboardData,
    KnowledgeBaseDashboardSchema,
    LastUploadSchema,
    SystemDashboardSchema,
)
from app.schemas.document import (
    DocumentDetailSchema,
    DocumentListData,
    DocumentListItemSchema,
    DocumentProcessingErrorSchema,
    PaginationSchema,
)
from app.schemas.settings import (
    AdminSettingsData,
    EditableSettingsSchema,
    ReadOnlySettingsSchema,
)


def dashboard_data(snapshot: DashboardSnapshot) -> DashboardData:
    return DashboardData(
        system=SystemDashboardSchema(**asdict(snapshot.system)),
        ai=AIDashboardSchema(**asdict(snapshot.ai)),
        knowledge_base=KnowledgeBaseDashboardSchema(**asdict(snapshot.knowledge_base)),
        last_upload=(
            LastUploadSchema(**asdict(snapshot.last_upload))
            if snapshot.last_upload is not None
            else None
        ),
    )


def settings_data(snapshot: SettingsSnapshot) -> AdminSettingsData:
    return AdminSettingsData(
        editable=EditableSettingsSchema(**asdict(snapshot.editable)),
        read_only=ReadOnlySettingsSchema(**asdict(snapshot.read_only)),
    )


def document_detail(view: DocumentView) -> DocumentDetailSchema:
    return DocumentDetailSchema(
        id=view.id,
        title=view.title,
        original_filename=view.original_filename,
        category=view.category,
        category_code=view.category_code,
        description=view.description,
        mime_type=view.mime_type,
        file_size_bytes=view.file_size_bytes,
        processing_status=view.processing_status,
        display_status=view.display_status,
        is_active=view.is_active,
        is_archived=view.is_archived,
        retrieval_eligible=view.retrieval_eligible,
        page_count=view.page_count,
        extracted_char_count=view.extracted_char_count,
        chunk_count=view.chunk_count,
        processing_error=(
            DocumentProcessingErrorSchema(**asdict(view.processing_error))
            if view.processing_error is not None
            else None
        ),
        uploaded_by=view.uploaded_by,
        processed_at=view.processed_at,
        activated_at=view.activated_at,
        archived_at=view.archived_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
        poll_after_seconds=view.poll_after_seconds,
    )


def document_list_item(view: DocumentView) -> DocumentListItemSchema:
    detail = document_detail(view)
    included_fields = set(DocumentListItemSchema.model_fields)
    return DocumentListItemSchema(**detail.model_dump(include=included_fields))


def document_list_data(page: DocumentPage) -> DocumentListData:
    return DocumentListData(
        documents=[document_list_item(item) for item in page.items],
        pagination=PaginationSchema(
            page=page.page,
            page_size=page.page_size,
            total_items=page.total_items,
            total_pages=page.total_pages,
            has_next=page.has_next,
            has_previous=page.has_previous,
        ),
    )
