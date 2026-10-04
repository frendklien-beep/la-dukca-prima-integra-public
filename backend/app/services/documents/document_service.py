import hashlib
import math

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError, document_error
from app.db.utc import utc_now
from app.domain.documents import DocumentPage, DocumentView, SafeProcessingError
from app.models.document import Document
from app.repositories.audit_repository import AuditRepository
from app.repositories.document_repository import DocumentRecord, DocumentRepository
from app.services.documents.document_categories import CATEGORY_LABELS, normalize_category
from app.services.documents.document_dispatcher import (
    DeferredDocumentProcessingDispatcher,
    ProcessingQueueFullError,
)
from app.services.documents.document_storage import DocumentStorage
from app.services.documents.document_types import (
    display_status,
    index_artifact_path,
    poll_after_seconds,
    retrieval_eligible,
)
from app.services.documents.document_validation import (
    normalize_description,
    normalize_original_filename,
    normalize_title,
    validate_declared_mime,
    validate_pdf_structure,
)

VALID_STATUSES = {"pending", "processing", "ready", "failed", "requires_ocr"}
VALID_SORTS = {"created_at", "updated_at", "title", "category", "processing_status"}


class DocumentService:
    def __init__(
        self,
        repository=None,
        audits=None,
        storage=None,
        dispatcher=None,
    ):
        self.repository = repository or DocumentRepository()
        self.audits = audits or AuditRepository()
        self.storage = storage or DocumentStorage()
        self.dispatcher = dispatcher or DeferredDocumentProcessingDispatcher()

    def _view(self, record: DocumentRecord) -> DocumentView:
        document = record.document
        processing_error = None
        has_safe_error = (
            document.processing_status in {"failed", "requires_ocr"}
            and document.processing_error_code
        )
        if has_safe_error:
            processing_error = SafeProcessingError(
                code=document.processing_error_code,
                message=document.processing_error_message
                or "Dokumen belum dapat diproses. Silakan coba kembali.",
            )
        return DocumentView(
            id=document.id,
            title=document.title,
            original_filename=document.original_filename,
            category=CATEGORY_LABELS[document.category],
            category_code=document.category,
            description=document.description,
            mime_type=document.mime_type,
            file_size_bytes=document.file_size_bytes,
            processing_status=document.processing_status,
            display_status=display_status(document),
            is_active=document.is_active,
            is_archived=document.archived_at is not None,
            retrieval_eligible=retrieval_eligible(document, record.chunk_count),
            page_count=document.page_count,
            extracted_char_count=document.extracted_char_count,
            chunk_count=record.chunk_count,
            processing_error=processing_error,
            uploaded_by=record.uploader_display_name,
            processed_at=document.processed_at,
            activated_at=document.activated_at,
            archived_at=document.archived_at,
            created_at=document.created_at,
            updated_at=document.updated_at,
            poll_after_seconds=poll_after_seconds(document),
        )

    def get_document(self, session: Session, document_id: int) -> DocumentView:
        record = self.repository.get_by_id(session, document_id)
        if record is None:
            raise document_error("DOCUMENT_NOT_FOUND", "Dokumen tidak ditemukan.", 404)
        return self._view(record)

    def list_documents(
        self,
        session: Session,
        *,
        page: int,
        page_size: int,
        search: str | None,
        category: str | None,
        processing_status: str | None,
        is_active: bool | None,
        include_archived: bool,
        sort_by: str,
        sort_order: str,
    ) -> DocumentPage:
        normalized_search = " ".join((search or "").strip().split()) or None
        category_code = normalize_category(category).code if category else None
        if processing_status is not None and processing_status not in VALID_STATUSES:
            raise document_error("VALIDATION_ERROR", "Status dokumen tidak valid.", 422)
        if sort_by not in VALID_SORTS or sort_order not in {"asc", "desc"}:
            raise document_error("VALIDATION_ERROR", "Urutan dokumen tidak valid.", 422)
        records, total = self.repository.list_paginated(
            session,
            page=page,
            page_size=page_size,
            search=normalized_search,
            category=category_code,
            processing_status=processing_status,
            is_active=is_active,
            include_archived=include_archived,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return DocumentPage(
            items=[self._view(record) for record in records],
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1 and total_pages > 0,
        )

    def upload_document(
        self,
        session: Session,
        *,
        upload: UploadFile,
        title: str,
        category: str,
        description: str | None,
        admin_id: int,
        request_id: str,
        settings: Settings,
    ) -> DocumentView:
        normalized_title = normalize_title(title)
        normalized_filename = normalize_original_filename(upload.filename)
        normalized_description = normalize_description(description)
        normalized_mime = validate_declared_mime(upload.content_type)
        category_meta = normalize_category(category)
        now = utc_now()
        keys = self.storage.prepare(settings, now)
        checksum = hashlib.sha256()
        total = 0
        try:
            with keys.temp_path.open("xb") as target:
                while True:
                    chunk = upload.file.read(settings.document_stream_chunk_bytes)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > settings.document_max_size_bytes:
                        raise document_error(
                            "FILE_TOO_LARGE",
                            "Ukuran PDF melebihi batas 100 MiB.",
                            413,
                        )
                    checksum.update(chunk)
                    target.write(chunk)
                target.flush()
            if total == 0:
                raise document_error("FILE_EMPTY", "File PDF kosong.", 422)
            page_count = validate_pdf_structure(
                keys.temp_path, max_pages=settings.document_max_pages
            )
            digest = checksum.hexdigest()

            moved = False
            try:
                with session.begin():
                    if self.repository.get_by_checksum_non_archived(session, digest) is not None:
                        raise document_error(
                            "DOCUMENT_DUPLICATE",
                            "Dokumen yang sama sudah tersedia.",
                            409,
                        )
                    document = Document(
                        title=normalized_title,
                        original_filename=normalized_filename,
                        storage_key=keys.storage_key,
                        mime_type=normalized_mime,
                        file_size_bytes=total,
                        sha256_checksum=digest,
                        category=category_meta.code,
                        description=normalized_description,
                        processing_status="pending",
                        is_active=False,
                        page_count=page_count,
                        extracted_char_count=None,
                        processing_error_code=None,
                        processing_error_message=None,
                        uploaded_by_admin_id=admin_id,
                        processing_started_at=None,
                        processed_at=None,
                        activated_at=None,
                        archived_at=None,
                        created_at=now,
                        updated_at=now,
                        authority_rank=category_meta.authority_rank,
                        document_number=None,
                        document_year=None,
                        issuer=None,
                        jurisdiction=category_meta.jurisdiction,
                        effective_date=None,
                        valid_until=None,
                        legal_status="unknown",
                        indexed_at=None,
                        index_version=None,
                        extraction_method=None,
                        text_quality_score=None,
                    )
                    self.repository.add(session, document)
                    self.storage.finalize(keys.temp_path, keys.final_path)
                    moved = True
                    self.audits.append_event(
                        session,
                        event_type="document.uploaded",
                        outcome="success",
                        request_id=request_id,
                        actor_admin_id=admin_id,
                        metadata={
                            "document_id": document.id,
                            "category_code": category_meta.code,
                            "file_size_bytes": total,
                            "processing_status": "pending",
                        },
                    )
            except IntegrityError as exc:
                if moved:
                    self.storage.remove(keys.final_path)
                raise document_error(
                    "DOCUMENT_DUPLICATE",
                    "Dokumen yang sama sudah tersedia.",
                    409,
                ) from exc
            except Exception:
                if moved:
                    self.storage.remove(keys.final_path)
                raise

            try:
                self.dispatcher.enqueue(document_id=document.id, request_id=request_id)
            except ProcessingQueueFullError:
                with session.begin():
                    self.audits.append_event(
                        session,
                        event_type="document.processing.dispatch_failed",
                        outcome="failure",
                        request_id=request_id,
                        actor_admin_id=admin_id,
                        metadata={
                            "document_id": document.id,
                            "processing_status": "pending",
                            "error_code": "PROCESSING_QUEUE_FULL",
                        },
                    )
            except Exception:
                with session.begin():
                    current = self.repository.get_entity(session, document.id)
                    if current is not None:
                        current.processing_status = "failed"
                        current.processing_started_at = None
                        current.processing_error_code = "PROCESSING_DISPATCH_FAILED"
                        current.processing_error_message = (
                            "Dokumen belum dapat diproses. Silakan coba kembali."
                        )
                        current.updated_at = utc_now()
                        self.audits.append_event(
                            session,
                            event_type="document.processing.dispatch_failed",
                            outcome="failure",
                            request_id=request_id,
                            actor_admin_id=admin_id,
                            metadata={
                                "document_id": document.id,
                                "processing_status": "failed",
                                "error_code": "PROCESSING_DISPATCH_FAILED",
                            },
                        )
            return self.get_document(session, document.id)
        except AppError:
            self.storage.remove(keys.temp_path)
            raise
        except OSError as exc:
            self.storage.remove(keys.temp_path)
            raise document_error(
                "DOCUMENT_STORAGE_UNAVAILABLE",
                "Penyimpanan dokumen tidak tersedia.",
                503,
                retryable=True,
            ) from exc
        finally:
            try:
                upload.file.close()
            except OSError:
                pass

    def activate_document(
        self,
        session: Session,
        *,
        document_id: int,
        admin_id: int,
        request_id: str,
        settings: Settings,
    ) -> DocumentView:
        with session.begin():
            document = self.repository.get_entity(session, document_id)
            if document is None:
                raise document_error("DOCUMENT_NOT_FOUND", "Dokumen tidak ditemukan.", 404)
            if document.archived_at is not None:
                raise document_error("DOCUMENT_ARCHIVED", "Dokumen sudah diarsipkan.", 409)
            if document.processing_status != "ready":
                raise document_error("DOCUMENT_NOT_READY", "Dokumen belum siap diaktifkan.", 409)
            chunk_count = len(document.chunks)
            artifact = index_artifact_path(settings.indexes_dir, document)
            if chunk_count <= 0 or artifact is None or not artifact.is_file():
                raise document_error(
                    "DOCUMENT_INDEX_NOT_READY",
                    "Indeks dokumen belum siap.",
                    409,
                )
            if document.legal_status in {"revoked", "superseded"}:
                raise document_error(
                    "DOCUMENT_LEGAL_STATUS_INVALID",
                    "Status hukum dokumen tidak dapat diaktifkan.",
                    409,
                )
            if not self.storage.resolve(settings, document.storage_key).is_file():
                raise document_error(
                    "DOCUMENT_STORAGE_UNAVAILABLE",
                    "Berkas dokumen tidak tersedia.",
                    503,
                )
            if not document.is_active:
                document.is_active = True
                document.activated_at = utc_now()
                document.updated_at = document.activated_at
                self.audits.append_event(
                    session,
                    event_type="document.activated",
                    outcome="success",
                    request_id=request_id,
                    actor_admin_id=admin_id,
                    metadata={"document_id": document.id},
                )
        return self.get_document(session, document_id)

    def deactivate_document(
        self,
        session: Session,
        *,
        document_id: int,
        admin_id: int,
        request_id: str,
    ) -> DocumentView:
        with session.begin():
            document = self.repository.get_entity(session, document_id)
            if document is None:
                raise document_error("DOCUMENT_NOT_FOUND", "Dokumen tidak ditemukan.", 404)
            if document.is_active:
                document.is_active = False
                document.updated_at = utc_now()
                self.audits.append_event(
                    session,
                    event_type="document.deactivated",
                    outcome="success",
                    request_id=request_id,
                    actor_admin_id=admin_id,
                    metadata={"document_id": document.id},
                )
        return self.get_document(session, document_id)

    def archive_document(
        self,
        session: Session,
        *,
        document_id: int,
        admin_id: int,
        request_id: str,
    ) -> DocumentView:
        with session.begin():
            document = self.repository.get_entity(session, document_id)
            if document is None:
                raise document_error("DOCUMENT_NOT_FOUND", "Dokumen tidak ditemukan.", 404)
            if document.archived_at is not None:
                pass
            elif document.processing_status == "processing":
                raise document_error("DOCUMENT_BUSY", "Dokumen sedang diproses.", 409)
            else:
                document.is_active = False
                document.archived_at = utc_now()
                document.updated_at = document.archived_at
                self.audits.append_event(
                    session,
                    event_type="document.archived",
                    outcome="success",
                    request_id=request_id,
                    actor_admin_id=admin_id,
                    metadata={"document_id": document.id},
                )
        return self.get_document(session, document_id)

    def retry_document(
        self,
        session: Session,
        *,
        document_id: int,
        admin_id: int,
        request_id: str,
    ) -> DocumentView:
        with session.begin():
            document = self.repository.get_entity(session, document_id)
            if document is None:
                raise document_error("DOCUMENT_NOT_FOUND", "Dokumen tidak ditemukan.", 404)
            if document.archived_at is not None:
                raise document_error("DOCUMENT_ARCHIVED", "Dokumen sudah diarsipkan.", 409)
            if document.processing_status == "processing":
                raise document_error("DOCUMENT_BUSY", "Dokumen sedang diproses.", 409)
            if document.processing_status != "failed":
                raise document_error(
                    "DOCUMENT_INVALID_STATE",
                    "Dokumen tidak dapat diproses ulang pada status saat ini.",
                    409,
                )
            document.processing_status = "pending"
            document.processing_error_code = None
            document.processing_error_message = None
            document.processing_started_at = None
            document.processed_at = None
            document.is_active = False
            document.updated_at = utc_now()
            self.audits.append_event(
                session,
                event_type="document.processing.retry_requested",
                outcome="success",
                request_id=request_id,
                actor_admin_id=admin_id,
                metadata={
                    "document_id": document.id,
                    "processing_status": "pending",
                },
            )
        self.dispatcher.enqueue(document_id=document_id, request_id=request_id)
        return self.get_document(session, document_id)


document_service = DocumentService()
