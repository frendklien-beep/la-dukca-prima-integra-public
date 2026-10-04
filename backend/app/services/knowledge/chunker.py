from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.models.document import Document
from app.services.knowledge.errors import ChunkingError
from app.services.knowledge.tokenizer import KnowledgeTokenizer
from app.services.knowledge.types import ExtractedPage, PreparedChunk

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n|(?<=\.)\n(?=[A-Z0-9])")


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    page_number: int
    section_title: str | None


def _embedding_prefix(document: Document, chunk: PreparedChunk) -> str:
    page_label = "-"
    if chunk.page_start is not None and chunk.page_end is not None:
        page_label = (
            str(chunk.page_start)
            if chunk.page_start == chunk.page_end
            else f"{chunk.page_start}-{chunk.page_end}"
        )
    source_type = document.category.replace("_", " ").upper()
    values = [
        f"SOURCE_TYPE: {source_type}",
        f"TITLE: {document.title}",
        f"ISSUER: {document.issuer or 'Dinas Dukcapil Kota Tomohon'}",
        f"JURISDICTION: {document.jurisdiction or '-'}",
        f"SECTION: {chunk.section_title or '-'}",
        f"PAGES: {page_label}",
        "",
        chunk.content,
    ]
    return "\n".join(values)


class DocumentChunker:
    def __init__(self, tokenizer: KnowledgeTokenizer) -> None:
        self.tokenizer = tokenizer

    def _units(self, pages: tuple[ExtractedPage, ...]) -> list[_Unit]:
        units: list[_Unit] = []
        current_section: str | None = None
        for page in pages:
            headings = set(page.headings)
            pending_heading: str | None = None
            parts = [part.strip() for part in _PARAGRAPH_SPLIT_RE.split(page.cleaned_text)]
            for part in parts:
                if not part:
                    continue
                lines = [line.strip() for line in part.splitlines() if line.strip()]
                if not lines:
                    continue
                substantive: list[str] = []
                for line in lines:
                    if line in headings:
                        current_section = line
                        pending_heading = line
                    else:
                        substantive.append(line)
                if not substantive:
                    continue
                text = "\n".join(substantive)
                if pending_heading:
                    text = f"{pending_heading}\n{text}"
                    pending_heading = None
                units.append(
                    _Unit(
                        text=text,
                        page_number=page.page_number,
                        section_title=current_section,
                    )
                )
        return units

    def _split_oversized(self, unit: _Unit, settings: Settings) -> list[_Unit]:
        tokens = self.tokenizer.encode(unit.text)
        if len(tokens) <= settings.chunk_max_tokens:
            return [unit]

        prefix = ""
        body_text = unit.text
        if unit.section_title and unit.text.startswith(f"{unit.section_title}\n"):
            prefix = f"{unit.section_title}\n"
            body_text = unit.text[len(prefix) :]
        prefix_tokens = self.tokenizer.encode(prefix) if prefix else []
        body_tokens = self.tokenizer.encode(body_text)
        budget = settings.chunk_max_tokens - len(prefix_tokens)
        if budget <= settings.chunk_overlap_tokens:
            raise ChunkingError("Judul bagian terlalu panjang untuk konfigurasi chunk.")
        step = budget - settings.chunk_overlap_tokens
        pieces: list[_Unit] = []
        start = 0
        while start < len(body_tokens):
            end = min(start + budget, len(body_tokens))
            body_piece = self.tokenizer.decode(body_tokens[start:end]).strip()
            text = f"{prefix}{body_piece}".strip()
            if text:
                pieces.append(
                    _Unit(
                        text=text,
                        page_number=unit.page_number,
                        section_title=unit.section_title,
                    )
                )
            if end == len(body_tokens):
                break
            start += step
        return pieces

    def prepare(
        self,
        document: Document,
        pages: tuple[ExtractedPage, ...],
        settings: Settings,
    ) -> tuple[PreparedChunk, ...]:
        raw_units = self._units(pages)
        units: list[_Unit] = []
        for unit in raw_units:
            units.extend(self._split_oversized(unit, settings))
        if not units:
            raise ChunkingError("Dokumen tidak menghasilkan konten chunk.")

        grouped: list[tuple[list[_Unit], int]] = []
        current: list[_Unit] = []
        current_tokens = 0
        for unit in units:
            unit_tokens = self.tokenizer.count(unit.text)
            if unit_tokens <= 0:
                continue
            same_section = not current or current[-1].section_title == unit.section_title
            would_exceed = current_tokens + unit_tokens > settings.chunk_max_tokens
            target_reached = current_tokens >= settings.chunk_target_tokens
            if current and (would_exceed or (target_reached and not same_section)):
                grouped.append((current, current_tokens))
                current = []
                current_tokens = 0
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            grouped.append((current, current_tokens))

        merged: list[tuple[list[_Unit], int]] = []
        for group, count in grouped:
            if (
                merged
                and count < settings.chunk_min_tokens
                and merged[-1][0][-1].section_title == group[0].section_title
                and merged[-1][1] + count <= settings.chunk_max_tokens
            ):
                previous, previous_count = merged[-1]
                merged[-1] = (previous + group, previous_count + count)
            else:
                merged.append((group, count))

        prepared: list[PreparedChunk] = []
        for index, (group, _estimated) in enumerate(merged):
            content = "\n\n".join(unit.text for unit in group).strip()
            token_count = self.tokenizer.count(content)
            if not content or token_count <= 0 or token_count > settings.chunk_max_tokens:
                raise ChunkingError()
            page_start = min(unit.page_number for unit in group)
            page_end = max(unit.page_number for unit in group)
            section = (
                group[0].section_title
                if all(unit.section_title == group[0].section_title for unit in group)
                else None
            )
            base = PreparedChunk(
                chunk_index=index,
                content=content,
                token_count=token_count,
                page_start=page_start,
                page_end=page_end,
                section_title=section,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                embedding_text="",
            )
            prepared.append(
                PreparedChunk(
                    chunk_index=base.chunk_index,
                    content=base.content,
                    token_count=base.token_count,
                    page_start=base.page_start,
                    page_end=base.page_end,
                    section_title=base.section_title,
                    content_hash=base.content_hash,
                    embedding_text=_embedding_prefix(document, base),
                )
            )
        if not prepared or [item.chunk_index for item in prepared] != list(range(len(prepared))):
            raise ChunkingError()
        return tuple(prepared)
