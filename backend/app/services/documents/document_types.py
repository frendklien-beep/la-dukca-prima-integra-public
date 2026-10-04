from pathlib import Path

from app.models.document import Document

TERMINAL_STATUSES = {"ready", "failed", "requires_ocr"}


def display_status(document: Document) -> str:
    if document.archived_at is not None:
        return "Arsip"
    if document.processing_status == "pending":
        return "Menunggu"
    if document.processing_status == "processing":
        return "Diproses"
    if document.processing_status == "ready":
        return "Aktif" if document.is_active else "Siap"
    if document.processing_status == "failed":
        return "Gagal"
    return "Memerlukan OCR"


def poll_after_seconds(document: Document) -> int | None:
    return 2 if document.processing_status in {"pending", "processing"} else None


def index_artifact_path(indexes_dir: Path, document: Document) -> Path | None:
    if not document.index_version:
        return None
    return indexes_dir / "documents" / str(document.id) / document.index_version / "embeddings.npy"


def retrieval_eligible(document: Document, chunk_count: int) -> bool:
    return (
        document.processing_status == "ready"
        and document.is_active
        and document.archived_at is None
        and document.legal_status not in {"revoked", "superseded"}
        and chunk_count > 0
        and document.index_version is not None
    )
