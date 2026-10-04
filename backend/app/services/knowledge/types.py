from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextLine:
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    font_flags: int
    page_height: float


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    raw_text: str
    cleaned_text: str
    headings: tuple[str, ...]
    char_count: int
    word_count: int
    image_block_count: int
    lines: tuple[TextLine, ...] = ()


@dataclass(frozen=True, slots=True)
class TextQuality:
    score: float
    total_chars: int
    total_words: int
    pages_with_text: int
    pages_without_text: int
    image_heavy_pages: int
    low_text_page_ratio: float
    pages_with_text_ratio: float
    replacement_character_ratio: float
    alphabetic_ratio: float
    classification: str


@dataclass(frozen=True, slots=True)
class PreparedChunk:
    chunk_index: int
    content: str
    token_count: int
    page_start: int | None
    page_end: int | None
    section_title: str | None
    content_hash: str
    embedding_text: str


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    vector_dimension: int
    request_ids: tuple[str, ...]
    input_tokens: int | None


@dataclass(frozen=True, slots=True)
class IndexMetadataRow:
    row_index: int
    chunk_id: int
    document_id: int
    chunk_index: int
    content_hash: str
    page_start: int | None
    page_end: int | None
    section_title: str | None


@dataclass(frozen=True, slots=True)
class PreparedIndex:
    document_id: int
    index_version: str
    vector_dimension: int
    chunk_count: int
    content_checksum: str
    version_dir: str
