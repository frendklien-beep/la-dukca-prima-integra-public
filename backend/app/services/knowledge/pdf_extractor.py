from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from app.core.config import Settings
from app.models.document import Document
from app.services.documents.document_storage import DocumentStorage
from app.services.knowledge.errors import ExtractionError
from app.services.knowledge.text_cleaner import finalize_pages, normalize_line
from app.services.knowledge.types import ExtractedPage, TextLine


class PdfExtractor:
    def __init__(self, storage: DocumentStorage | None = None) -> None:
        self.storage = storage or DocumentStorage()

    def resolve_and_validate_source(self, settings: Settings, document: Document) -> Path:
        if document.archived_at is not None:
            raise ExtractionError("DOCUMENT_ARCHIVED")
        if document.processing_status != "processing":
            raise ExtractionError("DOCUMENT_INVALID_STATE")
        try:
            path = self.storage.resolve(settings, document.storage_key)
        except Exception as exc:
            raise ExtractionError("UNSAFE_STORAGE_PATH") from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise ExtractionError("SOURCE_FILE_MISSING")
        if document.file_size_bytes and path.stat().st_size != document.file_size_bytes:
            raise ExtractionError("SOURCE_FILE_CHECKSUM_MISMATCH")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            signature = source.read(5)
            if signature != b"%PDF-":
                raise ExtractionError("PDF_INVALID_SIGNATURE")
            source.seek(0)
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != document.sha256_checksum:
            raise ExtractionError("SOURCE_FILE_CHECKSUM_MISMATCH")
        return path

    def extract(self, settings: Settings, document: Document) -> tuple[ExtractedPage, ...]:
        path = self.resolve_and_validate_source(settings, document)
        try:
            pdf = pymupdf.open(path)
        except Exception as exc:
            raise ExtractionError("PDF_CORRUPT") from exc
        try:
            if pdf.needs_pass:
                raise ExtractionError("PDF_PASSWORD_PROTECTED")
            if pdf.page_count <= 0:
                raise ExtractionError("PDF_EMPTY")
            if pdf.page_count > settings.document_max_pages:
                raise ExtractionError("PDF_PAGE_LIMIT_EXCEEDED")
            pages: list[ExtractedPage] = []
            for page_index in range(pdf.page_count):
                page = pdf.load_page(page_index)
                page_dict = page.get_text("dict", sort=True)
                page_height = float(page.rect.height)
                lines: list[TextLine] = []
                image_blocks = 0
                for block in page_dict.get("blocks", []):
                    if block.get("type") == 1:
                        image_blocks += 1
                        continue
                    if block.get("type") != 0:
                        continue
                    for raw_line in block.get("lines", []):
                        spans = raw_line.get("spans", [])
                        text = normalize_line("".join(str(span.get("text", "")) for span in spans))
                        if not text:
                            continue
                        sizes = [float(span.get("size", 0.0)) for span in spans]
                        flags = 0
                        for span in spans:
                            flags |= int(span.get("flags", 0))
                        bbox_raw = raw_line.get("bbox") or block.get("bbox") or (0, 0, 0, 0)
                        bbox = tuple(float(value) for value in bbox_raw[:4])
                        lines.append(
                            TextLine(
                                text=text,
                                bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                                font_size=max(sizes, default=0.0),
                                font_flags=flags,
                                page_height=page_height,
                            )
                        )
                raw_text = "\n".join(line.text for line in lines)
                pages.append(
                    ExtractedPage(
                        page_number=page_index + 1,
                        raw_text=raw_text,
                        cleaned_text="",
                        headings=(),
                        char_count=0,
                        word_count=0,
                        image_block_count=image_blocks,
                        lines=tuple(lines),
                    )
                )
            return finalize_pages(pages)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError() from exc
        finally:
            pdf.close()
