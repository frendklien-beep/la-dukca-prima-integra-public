import re
import unicodedata
from pathlib import Path

import pymupdf

from app.core.exceptions import document_error

PDF_MIME_TYPES = {"application/pdf", "application/x-pdf"}
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


def normalize_original_filename(value: str | None) -> str:
    if not value:
        raise document_error("FILENAME_INVALID", "Nama file PDF tidak valid.", 422)
    normalized = unicodedata.normalize("NFKC", value).replace("\x00", "").strip()
    if "/" in normalized or "\\" in normalized:
        raise document_error("FILENAME_INVALID", "Nama file PDF tidak valid.", 422)
    normalized = CONTROL_PATTERN.sub("", normalized).strip()
    if not normalized:
        normalized = "document.pdf"
    if len(normalized) > 255:
        stem = Path(normalized).stem[:250]
        normalized = f"{stem}.pdf"
    if Path(normalized).suffix.casefold() != ".pdf":
        raise document_error("UNSUPPORTED_MEDIA_TYPE", "File harus berformat PDF.", 415)
    return normalized


def normalize_title(value: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not 3 <= len(normalized) <= 255:
        raise document_error("VALIDATION_ERROR", "Judul harus 3-255 karakter.", 422)
    if CONTROL_PATTERN.search(normalized):
        raise document_error("VALIDATION_ERROR", "Judul memuat karakter tidak valid.", 422)
    return normalized


def normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    if len(normalized) > 2000:
        raise document_error("VALIDATION_ERROR", "Deskripsi maksimal 2000 karakter.", 422)
    if CONTROL_PATTERN.search(normalized.replace("\n", "").replace("\r", "")):
        raise document_error("VALIDATION_ERROR", "Deskripsi memuat karakter tidak valid.", 422)
    return normalized or None


def validate_declared_mime(value: str | None) -> str:
    normalized = (value or "").split(";", 1)[0].strip().casefold()
    if normalized not in PDF_MIME_TYPES:
        raise document_error("UNSUPPORTED_MEDIA_TYPE", "File harus berformat PDF.", 415)
    return normalized


def validate_pdf_structure(path: Path, *, max_pages: int) -> int:
    try:
        with path.open("rb") as handle:
            signature = handle.read(5)
        if signature != b"%PDF-":
            raise document_error("PDF_INVALID_SIGNATURE", "File PDF tidak valid.", 415)
        document = pymupdf.open(path)
        try:
            if document.needs_pass:
                raise document_error(
                    "PDF_ENCRYPTED",
                    "PDF yang dilindungi password tidak dapat digunakan.",
                    422,
                )
            page_count = document.page_count
            if page_count <= 0:
                raise document_error("PDF_EMPTY", "PDF tidak memiliki halaman.", 422)
            if page_count > max_pages:
                raise document_error(
                    "PDF_PAGE_LIMIT_EXCEEDED",
                    f"PDF melebihi batas {max_pages} halaman.",
                    422,
                )
            return page_count
        finally:
            document.close()
    except pymupdf.FileDataError as exc:
        raise document_error("PDF_CORRUPT", "PDF rusak atau tidak dapat dibuka.", 422) from exc
