from __future__ import annotations

from app.core.config import Settings
from app.services.knowledge.errors import GarbledTextError, RequiresOcrError
from app.services.knowledge.types import ExtractedPage, TextQuality


def evaluate_text_quality(pages: tuple[ExtractedPage, ...], settings: Settings) -> TextQuality:
    page_count = len(pages)
    total_chars = sum(page.char_count for page in pages)
    total_words = sum(page.word_count for page in pages)
    pages_with_text = sum(page.char_count >= settings.pdf_min_page_text_chars for page in pages)
    pages_without_text = page_count - pages_with_text
    image_heavy_pages = sum(
        page.image_block_count > 0 and page.char_count < settings.pdf_min_page_text_chars
        for page in pages
    )
    low_text_ratio = pages_without_text / page_count if page_count else 1.0
    text_ratio = pages_with_text / page_count if page_count else 0.0
    combined = "".join(page.cleaned_text for page in pages)
    replacement_ratio = combined.count("�") / max(len(combined), 1)
    alphabetic_ratio = sum(char.isalpha() for char in combined) / max(len(combined), 1)

    short_one_page_digital = (
        page_count == 1
        and pages_with_text == 1
        and total_chars >= settings.pdf_min_page_text_chars
        and image_heavy_pages == 0
    )
    scan_like = (
        (total_chars < settings.pdf_min_total_extracted_chars and not short_one_page_digital)
        or text_ratio < settings.pdf_min_pages_with_text_ratio
        or low_text_ratio > settings.pdf_max_low_text_page_ratio
    )
    garbled = total_chars >= settings.pdf_min_total_extracted_chars and (
        replacement_ratio > settings.pdf_max_replacement_character_ratio
        or alphabetic_ratio < settings.pdf_min_alphabetic_ratio
    )
    if garbled:
        classification = "garbled"
    elif scan_like:
        classification = "requires_ocr"
    else:
        classification = "digital_text"

    score_parts = [
        min(total_chars / max(settings.pdf_min_total_extracted_chars, 1), 1.0),
        text_ratio,
        1.0 - min(replacement_ratio / max(settings.pdf_max_replacement_character_ratio, 1e-9), 1.0),
        min(alphabetic_ratio / max(settings.pdf_min_alphabetic_ratio, 1e-9), 1.0),
    ]
    score = max(0.0, min(sum(score_parts) / len(score_parts), 1.0))
    return TextQuality(
        score=round(score, 6),
        total_chars=total_chars,
        total_words=total_words,
        pages_with_text=pages_with_text,
        pages_without_text=pages_without_text,
        image_heavy_pages=image_heavy_pages,
        low_text_page_ratio=low_text_ratio,
        pages_with_text_ratio=text_ratio,
        replacement_character_ratio=replacement_ratio,
        alphabetic_ratio=alphabetic_ratio,
        classification=classification,
    )


def enforce_text_quality(quality: TextQuality) -> None:
    if quality.classification == "requires_ocr":
        raise RequiresOcrError()
    if quality.classification == "garbled":
        raise GarbledTextError()
