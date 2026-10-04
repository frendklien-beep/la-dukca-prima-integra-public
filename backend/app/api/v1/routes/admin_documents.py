from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthContext, get_current_admin_context
from app.api.dependencies.database import get_db_session
from app.api.dependencies.security import require_admin_mutation_context
from app.api.v1.routes._mappers import document_detail, document_list_data
from app.schemas.common import success_envelope
from app.schemas.document import (
    DocumentActionData,
    DocumentActionResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentUploadData,
    DocumentUploadResponse,
)
from app.services.documents.document_service import document_service

router = APIRouter()


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    operation_id="admin_list_documents",
    summary="Daftar dokumen Knowledge Base",
)
def list_documents(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    category: str | None = None,
    processing_status: str | None = None,
    is_active: bool | None = None,
    include_archived: bool = False,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db_session),
    _context: AuthContext = Depends(get_current_admin_context),
):
    result = document_service.list_documents(
        db,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        processing_status=processing_status,
        is_active=is_active,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return success_envelope(request.state.request_id, document_list_data(result))


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    status_code=202,
    operation_id="admin_upload_document",
    summary="Unggah satu PDF resmi",
)
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(require_admin_mutation_context),
):
    view = document_service.upload_document(
        db,
        upload=file,
        title=title,
        category=category,
        description=description,
        admin_id=context.admin.id,
        request_id=request.state.request_id,
        settings=request.app.state.settings,
    )
    return success_envelope(
        request.state.request_id,
        DocumentUploadData(document=document_detail(view), poll_after_seconds=2),
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailResponse,
    operation_id="admin_get_document",
    summary="Detail dan status pemrosesan dokumen",
)
def get_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    _context: AuthContext = Depends(get_current_admin_context),
):
    view = document_service.get_document(db, document_id)
    return success_envelope(request.state.request_id, document_detail(view))


def _action_response(request: Request, view):
    return success_envelope(
        request.state.request_id,
        DocumentActionData(document=document_detail(view)),
    )


@router.post(
    "/documents/{document_id}/activate",
    response_model=DocumentActionResponse,
    operation_id="admin_activate_document",
)
def activate_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(require_admin_mutation_context),
):
    view = document_service.activate_document(
        db,
        document_id=document_id,
        admin_id=context.admin.id,
        request_id=request.state.request_id,
        settings=request.app.state.settings,
    )
    return _action_response(request, view)


@router.post(
    "/documents/{document_id}/deactivate",
    response_model=DocumentActionResponse,
    operation_id="admin_deactivate_document",
)
def deactivate_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(require_admin_mutation_context),
):
    view = document_service.deactivate_document(
        db,
        document_id=document_id,
        admin_id=context.admin.id,
        request_id=request.state.request_id,
    )
    return _action_response(request, view)


@router.post(
    "/documents/{document_id}/archive",
    response_model=DocumentActionResponse,
    operation_id="admin_archive_document",
)
def archive_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(require_admin_mutation_context),
):
    view = document_service.archive_document(
        db,
        document_id=document_id,
        admin_id=context.admin.id,
        request_id=request.state.request_id,
    )
    return _action_response(request, view)


@router.post(
    "/documents/{document_id}/retry",
    response_model=DocumentActionResponse,
    status_code=202,
    operation_id="admin_retry_document",
)
def retry_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(require_admin_mutation_context),
):
    view = document_service.retry_document(
        db,
        document_id=document_id,
        admin_id=context.admin.id,
        request_id=request.state.request_id,
    )
    return _action_response(request, view)
