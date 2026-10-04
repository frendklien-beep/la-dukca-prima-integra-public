from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.utc import utc_now
from app.models.document import Document
from app.repositories.audit_repository import AuditRepository
from app.repositories.processing_repository import ProcessingRepository
from app.services.knowledge.chunker import DocumentChunker
from app.services.knowledge.embedding import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    normalized_matrix,
)
from app.services.knowledge.errors import (
    EmbeddingError,
    KnowledgeProcessingError,
    RequiresOcrError,
)
from app.services.knowledge.index_store import IndexPromotion, KnowledgeIndexStore
from app.services.knowledge.pdf_extractor import PdfExtractor
from app.services.knowledge.text_quality import enforce_text_quality, evaluate_text_quality
from app.services.knowledge.tokenizer import KnowledgeTokenizer
from app.services.knowledge.types import PreparedChunk

logger = logging.getLogger(__name__)


class UnconfiguredEmbeddingProvider:
    async def embed(self, texts):
        del texts
        raise EmbeddingError("Konfigurasi embedding belum tersedia.")


class DocumentProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        repository: ProcessingRepository | None = None,
        audits: AuditRepository | None = None,
        extractor: PdfExtractor | None = None,
        tokenizer_factory: Callable[[str], KnowledgeTokenizer] = KnowledgeTokenizer,
        embedding_provider: EmbeddingProvider | None = None,
        index_store: KnowledgeIndexStore | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.repository = repository or ProcessingRepository()
        self.audits = audits or AuditRepository()
        self.extractor = extractor or PdfExtractor()
        self.tokenizer_factory = tokenizer_factory
        self.embedding_provider = embedding_provider or self._default_embedding_provider()
        self.index_store = index_store or KnowledgeIndexStore(settings)

    def _default_embedding_provider(self) -> EmbeddingProvider:
        try:
            return OpenAIEmbeddingProvider(self.settings)
        except EmbeddingError:
            return UnconfiguredEmbeddingProvider()

    async def close(self) -> None:
        close = getattr(self.embedding_provider, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result

    def _claim(self, document_id: int, request_id: str) -> Document | None:
        now = utc_now()
        with self.session_factory() as session:
            with session.begin():
                if not self.repository.claim_pending(session, document_id, now):
                    return None
                document = self.repository.get_document(session, document_id)
                if document is None:
                    return None
                self.audits.append_event(
                    session,
                    event_type="document.processing.started",
                    outcome="success",
                    request_id=request_id,
                    metadata={
                        "document_id": document_id,
                        "processing_status": "processing",
                    },
                )
            session.expunge(document)
            return document

    def _mark_terminal(
        self,
        *,
        document_id: int,
        request_id: str,
        status: str,
        code: str,
        message: str,
        clear_artifacts: bool,
    ) -> None:
        old_version: str | None = None
        with self.session_factory() as session:
            with session.begin():
                document = self.repository.get_document(session, document_id)
                if document is None or document.processing_status != "processing":
                    return
                old_version = document.index_version
                if clear_artifacts:
                    self.repository.replace_chunks(session, document_id, (), utc_now())
                    document.indexed_at = None
                    document.index_version = None
                document.processing_status = status
                document.processing_started_at = None
                document.processing_error_code = code
                document.processing_error_message = message
                document.processed_at = utc_now()
                document.is_active = False
                document.updated_at = document.processed_at
                self.audits.append_event(
                    session,
                    event_type=(
                        "document.processing.requires_ocr"
                        if status == "requires_ocr"
                        else "document.processing.failed"
                    ),
                    outcome="failure",
                    request_id=request_id,
                    metadata={
                        "document_id": document_id,
                        "processing_status": status,
                        "error_code": code,
                    },
                )
        if clear_artifacts and old_version:
            self.index_store.remove_document_version(document_id, old_version)

    def _finalize_success(
        self,
        *,
        document_id: int,
        request_id: str,
        page_count: int,
        quality_score: float,
        extracted_char_count: int,
        chunks: tuple[PreparedChunk, ...],
        matrix,
    ) -> None:
        session = self.session_factory()
        promotion: IndexPromotion | None = None
        old_version: str | None = None
        index_version = uuid4().hex
        try:
            transaction = session.begin()
            document = self.repository.get_document(session, document_id)
            if (
                document is None
                or document.processing_status != "processing"
                or document.archived_at is not None
            ):
                transaction.rollback()
                return
            old_version = document.index_version
            now = utc_now()
            entities = self.repository.replace_chunks(session, document_id, chunks, now)
            chunk_ids = tuple(int(entity.id) for entity in entities)
            prepared_index, promotion = self.index_store.promote(
                document_id=document_id,
                index_version=index_version,
                matrix=matrix,
                chunks=chunks,
                chunk_ids=chunk_ids,
            )
            document.processing_status = "ready"
            document.processing_started_at = None
            document.processing_error_code = None
            document.processing_error_message = None
            document.is_active = False
            document.page_count = page_count
            document.extracted_char_count = extracted_char_count
            document.processed_at = now
            document.indexed_at = now
            document.index_version = prepared_index.index_version
            document.extraction_method = "pymupdf_text"
            document.text_quality_score = quality_score
            document.updated_at = now
            self.audits.append_event(
                session,
                event_type="document.processing.completed",
                outcome="success",
                request_id=request_id,
                metadata={
                    "document_id": document_id,
                    "processing_status": "ready",
                    "page_count": page_count,
                    "chunk_count": len(chunks),
                    "pipeline_version": self.settings.knowledge_pipeline_version,
                    "vector_dimension": prepared_index.vector_dimension,
                },
            )
            transaction.commit()
            promotion.commit()
        except Exception:
            session.rollback()
            if promotion is not None:
                promotion.rollback()
            raise
        finally:
            session.close()
        if old_version and old_version != index_version:
            self.index_store.remove_document_version(document_id, old_version)

    def _log_result(
        self,
        *,
        document_id: int,
        request_id: str,
        stage: str,
        status: str,
        started_at: float,
        error_code: str | None = None,
        page_count: int | None = None,
        chunk_count: int | None = None,
        embedding_batch_count: int | None = None,
    ) -> None:
        logger.info(
            "document_processing_result "
            "request_id=%s document_id=%s pipeline_version=%s "
            "processing_stage=%s duration_ms=%s page_count=%s chunk_count=%s "
            "embedding_batch_count=%s result_status=%s error_code=%s",
            request_id,
            document_id,
            self.settings.knowledge_pipeline_version,
            stage,
            round((time.perf_counter() - started_at) * 1000),
            page_count,
            chunk_count,
            embedding_batch_count,
            status,
            error_code,
        )

    async def process(self, *, document_id: int, request_id: str) -> None:
        started_at = time.perf_counter()
        stage = "claim"
        page_count: int | None = None
        chunk_count: int | None = None
        embedding_batch_count: int | None = None
        document = await asyncio.to_thread(self._claim, document_id, request_id)
        if document is None:
            self._log_result(
                document_id=document_id,
                request_id=request_id,
                stage=stage,
                status="skipped",
                started_at=started_at,
            )
            return
        try:
            stage = "extract"
            pages = await asyncio.to_thread(self.extractor.extract, self.settings, document)
            page_count = len(pages)
            stage = "quality"
            quality = evaluate_text_quality(pages, self.settings)
            enforce_text_quality(quality)
            stage = "chunk"
            tokenizer = self.tokenizer_factory(self.settings.openai_chat_model)
            chunker = DocumentChunker(tokenizer)
            chunks = await asyncio.to_thread(chunker.prepare, document, pages, self.settings)
            chunk_count = len(chunks)
            stage = "embed"
            embeddings = await self.embedding_provider.embed(
                [chunk.embedding_text for chunk in chunks]
            )
            embedding_batch_count = max(len(embeddings.request_ids), 1)
            matrix = normalized_matrix(embeddings)
            stage = "index_and_commit"
            await asyncio.to_thread(
                self._finalize_success,
                document_id=document_id,
                request_id=request_id,
                page_count=page_count,
                quality_score=quality.score,
                extracted_char_count=quality.total_chars,
                chunks=chunks,
                matrix=matrix,
            )
            self._log_result(
                document_id=document_id,
                request_id=request_id,
                stage=stage,
                status="ready",
                started_at=started_at,
                page_count=page_count,
                chunk_count=chunk_count,
                embedding_batch_count=embedding_batch_count,
            )
        except RequiresOcrError as exc:
            await asyncio.to_thread(
                self._mark_terminal,
                document_id=document_id,
                request_id=request_id,
                status="requires_ocr",
                code=exc.code,
                message=exc.safe_message,
                clear_artifacts=True,
            )
            self._log_result(
                document_id=document_id,
                request_id=request_id,
                stage=stage,
                status="requires_ocr",
                started_at=started_at,
                error_code=exc.code,
                page_count=page_count,
                chunk_count=chunk_count,
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                asyncio.to_thread(
                    self._mark_terminal,
                    document_id=document_id,
                    request_id=request_id,
                    status="failed",
                    code="PROCESSING_INTERRUPTED",
                    message="Pemrosesan dokumen terhenti dan perlu dicoba kembali.",
                    clear_artifacts=False,
                )
            )
            self._log_result(
                document_id=document_id,
                request_id=request_id,
                stage=stage,
                status="failed",
                started_at=started_at,
                error_code="PROCESSING_INTERRUPTED",
                page_count=page_count,
                chunk_count=chunk_count,
            )
            raise
        except KnowledgeProcessingError as exc:
            await asyncio.to_thread(
                self._mark_terminal,
                document_id=document_id,
                request_id=request_id,
                status="failed",
                code=exc.code,
                message=exc.safe_message,
                clear_artifacts=False,
            )
            self._log_result(
                document_id=document_id,
                request_id=request_id,
                stage=stage,
                status="failed",
                started_at=started_at,
                error_code=exc.code,
                page_count=page_count,
                chunk_count=chunk_count,
                embedding_batch_count=embedding_batch_count,
            )
        except Exception:
            logger.exception(
                "document_processing_unhandled document_id=%s request_id=%s",
                document_id,
                request_id,
            )
            await asyncio.to_thread(
                self._mark_terminal,
                document_id=document_id,
                request_id=request_id,
                status="failed",
                code="PDF_EXTRACTION_FAILED",
                message="Dokumen belum dapat diproses. Silakan coba kembali.",
                clear_artifacts=False,
            )
            self._log_result(
                document_id=document_id,
                request_id=request_id,
                stage=stage,
                status="failed",
                started_at=started_at,
                error_code="PDF_EXTRACTION_FAILED",
                page_count=page_count,
                chunk_count=chunk_count,
                embedding_batch_count=embedding_batch_count,
            )
