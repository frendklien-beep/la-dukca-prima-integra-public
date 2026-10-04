from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.core.config import Settings
from app.db.utc import utc_now
from app.repositories.audit_repository import AuditRepository
from app.repositories.processing_repository import ProcessingRepository
from app.services.documents.document_storage import DocumentStorage
from app.services.knowledge.processor import DocumentProcessor

logger = logging.getLogger(__name__)


class ProcessingQueueFullError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentProcessingJob:
    document_id: int
    request_id: str


class DocumentProcessingDispatcher(Protocol):
    def enqueue(self, *, document_id: int, request_id: str) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def recover_pending(self) -> None: ...


class DeferredDocumentProcessingDispatcher:
    """Testing and pre-runtime dispatcher that preserves pending state."""

    def enqueue(self, *, document_id: int, request_id: str) -> None:
        del document_id, request_id

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def recover_pending(self) -> None:
        return None


class InProcessDocumentProcessingDispatcher:
    _STOP = object()

    def __init__(
        self,
        *,
        settings: Settings,
        processor: DocumentProcessor,
        session_factory,
        repository: ProcessingRepository | None = None,
        audits: AuditRepository | None = None,
        storage: DocumentStorage | None = None,
    ) -> None:
        self.settings = settings
        self.processor = processor
        self.session_factory = session_factory
        self.repository = repository or ProcessingRepository()
        self.audits = audits or AuditRepository()
        self.storage = storage or DocumentStorage()
        self._queue: queue.Queue[DocumentProcessingJob | object] = queue.Queue(
            maxsize=settings.processing_queue_max_size
        )
        self._queued_ids: set[int] = set()
        self._lock = threading.Lock()
        self._workers: list[asyncio.Task] = []
        self._accepting = False

    def enqueue(self, *, document_id: int, request_id: str) -> None:
        if document_id <= 0:
            raise ValueError("document_id harus positif")
        if not self._accepting:
            raise RuntimeError("processing dispatcher belum aktif")
        with self._lock:
            if document_id in self._queued_ids:
                return
            job = DocumentProcessingJob(document_id=document_id, request_id=request_id)
            try:
                self._queue.put_nowait(job)
            except queue.Full as exc:
                raise ProcessingQueueFullError("processing queue penuh") from exc
            self._queued_ids.add(document_id)

    async def start(self) -> None:
        if self._workers:
            return
        self._accepting = True
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"document-processor-{index}")
            for index in range(self.settings.processing_worker_count)
        ]

    async def _worker(self, worker_index: int) -> None:
        del worker_index
        while True:
            item = await asyncio.to_thread(self._queue.get)
            if item is self._STOP:
                self._queue.task_done()
                break
            if not isinstance(item, DocumentProcessingJob):
                logger.error(
                    "document_processing_invalid_queue_item type=%s",
                    type(item).__name__,
                )
                self._queue.task_done()
                continue
            try:
                await asyncio.wait_for(
                    self.processor.process(
                        document_id=item.document_id,
                        request_id=item.request_id,
                    ),
                    timeout=self.settings.processing_job_timeout_seconds,
                )
            except TimeoutError:
                logger.error(
                    "document_processing_timeout document_id=%s request_id=%s",
                    item.document_id,
                    item.request_id,
                )
            except Exception:
                logger.exception(
                    "document_processing_worker_error document_id=%s request_id=%s",
                    item.document_id,
                    item.request_id,
                )
            finally:
                with self._lock:
                    self._queued_ids.discard(item.document_id)
                self._queue.task_done()

    def _recover_database_state(self) -> list[int]:
        cutoff = utc_now() - timedelta(minutes=self.settings.processing_stale_after_minutes)
        pending: list[int] = []
        with self.session_factory() as session:
            with session.begin():
                stale = self.repository.stale_processing_ids(
                    session, cutoff, self.settings.processing_recovery_batch_size
                )
                for document_id in stale:
                    document = self.repository.get_document(session, document_id)
                    if document is None:
                        continue
                    document.processing_status = "failed"
                    document.processing_started_at = None
                    document.processing_error_code = "PROCESSING_INTERRUPTED"
                    document.processing_error_message = (
                        "Pemrosesan dokumen terhenti dan perlu dicoba kembali."
                    )
                    document.processed_at = utc_now()
                    document.updated_at = document.processed_at
                    self.audits.append_event(
                        session,
                        event_type="document.processing.interrupted",
                        outcome="failure",
                        request_id="startup-recovery",
                        metadata={
                            "document_id": document_id,
                            "processing_status": "failed",
                            "error_code": "PROCESSING_INTERRUPTED",
                        },
                    )
                candidate_ids = self.repository.pending_ids(
                    session, self.settings.processing_recovery_batch_size
                )
                for document_id in candidate_ids:
                    document = self.repository.get_document(session, document_id)
                    if document is None:
                        continue
                    try:
                        source = self.storage.resolve(self.settings, document.storage_key)
                    except Exception:
                        logger.warning(
                            "document_recovery_storage_resolve_failed document_id=%s",
                            document_id,
                            exc_info=True,
                        )
                        source = None
                    if source is not None and source.is_file():
                        pending.append(document_id)
        return pending

    async def recover_pending(self) -> None:
        pending = await asyncio.to_thread(self._recover_database_state)
        for document_id in pending:
            try:
                self.enqueue(document_id=document_id, request_id="startup-recovery")
            except ProcessingQueueFullError:
                break

    async def stop(self) -> None:
        self._accepting = False
        if not self._workers:
            await self.processor.close()
            return
        for _worker in self._workers:
            await asyncio.to_thread(self._queue.put, self._STOP)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True),
                timeout=min(self.settings.processing_job_timeout_seconds, 30),
            )
        except TimeoutError:
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
        finally:
            self._workers.clear()
            await self.processor.close()
