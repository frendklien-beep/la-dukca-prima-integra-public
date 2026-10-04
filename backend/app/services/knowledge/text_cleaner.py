from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from app.services.knowledge.types import ExtractedPage, TextLine

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_LEGAL_HEADING_RE = re.compile(
    r"^(?:BAB\s+[IVXLCDM]+|BAGIAN\s+\S+|PARAGRAF\s+\d+|PASAL\s+\d+|"
    r"[A-Z]\.|\d+\.)\s*",
    re.IGNORECASE,
)
_PROTECTED_REPEAT_RE = re.compile(
    r"^(?:BAB\b|PASAL\b|BAGIAN\b|PARAGRAF\b|UNDANG-UNDANG\b|PERATURAN\b|"
    r"KEPUTUSAN\b|PERSYARATAN\b|PROSEDUR\b)",
    re.IGNORECASE,
)


def normalize_line(text: str) -> str:
    value = unicodedata.normalize("NFKC", text)
    value = _CONTROL_RE.sub("", value)
    value = _SPACE_RE.sub(" ", value)
    return value.strip()


def _repeat_key(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_line(text)).casefold()


def detect_repeated_marginal_lines(pages: list[tuple[float, list[TextLine]]]) -> set[str]:
    if len(pages) < 2:
        return set()
    occurrences: Counter[str] = Counter()
    per_page: list[set[str]] = []
    for page_height, lines in pages:
        candidates: set[str] = set()
        for line in lines:
            text = normalize_line(line.text)
            if not text or len(text) > 120 or _PROTECTED_REPEAT_RE.match(text):
                continue
            top = line.bbox[1]
            bottom = line.bbox[3]
            near_margin = top <= page_height * 0.12 or bottom >= page_height * 0.88
            if near_margin:
                candidates.add(_repeat_key(text))
        per_page.append(candidates)
    for candidates in per_page:
        occurrences.update(candidates)
    threshold = max(2, math.ceil(len(pages) * 0.60))
    return {key for key, count in occurrences.items() if count >= threshold}


def _safe_dehyphenate(text: str) -> str:
    pattern = re.compile(r"(?P<word>[A-Za-zÀ-ÿ]{2,})-\n(?P<next>[a-zà-ÿ][A-Za-zÀ-ÿ]*)")

    def join(match: re.Match[str]) -> str:
        word = match.group("word")
        following = match.group("next")
        if not any(char.islower() for char in word):
            return match.group(0)
        if word.casefold() in {"ktp", "non", "anak"}:
            return match.group(0)
        return f"{word}{following}"

    return pattern.sub(join, text)


def clean_page_lines(lines: tuple[TextLine, ...], repeated_margins: set[str]) -> str:
    kept: list[str] = []
    for line in lines:
        normalized = normalize_line(line.text)
        if not normalized:
            continue
        if _repeat_key(normalized) in repeated_margins:
            continue
        kept.append(normalized)
    text = "\n".join(kept)
    text = _safe_dehyphenate(text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def _uppercase_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(char.isupper() for char in letters) / len(letters)


def detect_headings(lines: tuple[TextLine, ...]) -> tuple[str, ...]:
    meaningful = [line for line in lines if normalize_line(line.text)]
    if not meaningful:
        return ()
    ordered_sizes = sorted(line.font_size for line in meaningful if line.font_size > 0)
    median_size = ordered_sizes[len(ordered_sizes) // 2] if ordered_sizes else 0.0
    headings: list[str] = []
    for line in meaningful:
        text = normalize_line(line.text)
        if not text or len(text) > 180:
            continue
        known = bool(_LEGAL_HEADING_RE.match(text))
        is_bold = bool(line.font_flags & 16)
        is_large = median_size > 0 and line.font_size >= median_size * 1.15
        centered = abs((line.bbox[0] + line.bbox[2]) / 2 - 297.5) <= 90
        upper = _uppercase_ratio(text) >= 0.75 and len(text) >= 4
        score = sum((known, is_bold, is_large, centered, upper))
        if known or score >= 2:
            if text not in headings:
                headings.append(text)
    return tuple(headings)


def finalize_pages(raw_pages: list[ExtractedPage]) -> tuple[ExtractedPage, ...]:
    marginal_input = [
        ((page.lines[0].page_height if page.lines else 0.0), list(page.lines)) for page in raw_pages
    ]
    repeated = detect_repeated_marginal_lines(marginal_input)
    cleaned: list[ExtractedPage] = []
    for page in raw_pages:
        text = clean_page_lines(page.lines, repeated)
        headings = detect_headings(page.lines)
        cleaned.append(
            ExtractedPage(
                page_number=page.page_number,
                raw_text=page.raw_text,
                cleaned_text=text,
                headings=headings,
                char_count=len(text),
                word_count=len(text.split()),
                image_block_count=page.image_block_count,
                lines=page.lines,
            )
        )
    return tuple(cleaned)
