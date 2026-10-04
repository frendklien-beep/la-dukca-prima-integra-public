from __future__ import annotations


class KnowledgeProcessingError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class RequiresOcrError(KnowledgeProcessingError):
    def __init__(self) -> None:
        super().__init__(
            "PDF_TEXT_TOO_LOW",
            "Dokumen tidak memiliki teks digital yang cukup dan memerlukan OCR.",
        )


class GarbledTextError(KnowledgeProcessingError):
    def __init__(self) -> None:
        super().__init__(
            "PDF_TEXT_GARBLED",
            "Teks PDF tidak dapat dibaca dengan baik.",
        )


class ExtractionError(KnowledgeProcessingError):
    def __init__(self, code: str = "PDF_EXTRACTION_FAILED") -> None:
        messages = {
            "SOURCE_FILE_MISSING": "Berkas sumber dokumen tidak ditemukan.",
            "SOURCE_FILE_CHECKSUM_MISMATCH": "Integritas berkas sumber tidak sesuai.",
            "PDF_INVALID_SIGNATURE": "Berkas tidak memiliki format PDF yang valid.",
            "PDF_CORRUPT": "Berkas PDF rusak atau tidak dapat dibuka.",
            "PDF_ENCRYPTED": "PDF terenkripsi tidak dapat diproses.",
            "PDF_PAGE_LIMIT_EXCEEDED": "Jumlah halaman PDF melebihi batas.",
            "PDF_EMPTY": "PDF tidak memiliki halaman.",
            "DOCUMENT_INVALID_STATE": "Status dokumen tidak dapat diproses.",
            "DOCUMENT_ARCHIVED": "Dokumen telah diarsipkan.",
            "UNSAFE_STORAGE_PATH": "Lokasi berkas dokumen tidak valid.",
        }
        super().__init__(code, messages.get(code, "Ekstraksi PDF gagal dilakukan."))


class ChunkingError(KnowledgeProcessingError):
    def __init__(self, message: str = "Pembuatan potongan dokumen gagal.") -> None:
        super().__init__("PDF_CHUNKING_FAILED", message)


class TokenizerUnavailableError(ChunkingError):
    def __init__(self) -> None:
        super().__init__("Tokenizer dokumen tidak tersedia.")


class EmbeddingError(KnowledgeProcessingError):
    def __init__(self, message: str = "Layanan embedding belum dapat digunakan.") -> None:
        super().__init__("EMBEDDING_REQUEST_FAILED", message)


class IndexWriteError(KnowledgeProcessingError):
    def __init__(self) -> None:
        super().__init__("INDEX_WRITE_FAILED", "Indeks dokumen gagal disimpan.")
