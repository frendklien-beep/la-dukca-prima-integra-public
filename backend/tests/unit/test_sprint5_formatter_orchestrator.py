from dataclasses import replace
from datetime import date

import pytest

from app.domain.conversation import (
    IntentRetrievalQuery,
    IntentRetrievalResult,
    PlannedIntent,
    ResponseSection,
    SourceContext,
)
from app.schemas.generated_chat import (
    GeneratedConversationAnswer,
    GeneratedIntentAnswer,
)
from app.services.conversation.formatter import MarkdownFormatter
from app.services.conversation.orchestrator import ResponseOrchestrator
from app.services.conversation.validation import (
    sanitize_markdown,
    validate_grounded_claims,
)


def _source(intent_id: str, key: str, *, chunk_id: int = 10) -> SourceContext:
    return SourceContext(
        source_key=key,
        intent_id=intent_id,
        document_id=1,
        chunk_id=chunk_id,
        title="SOP Pelayanan KTP Elektronik",
        category="sop",
        authority_rank=6,
        jurisdiction="city",
        effective_date=date(2026, 1, 1),
        page_start=2,
        page_end=3,
        section_title="Persyaratan",
        content="Pelayanan gratis. Waktu penyelesaian 1 hari kerja. Permendagri 108 Tahun 2019.",
        score=0.91,
    )


def _plan(intent_id: str, heading: str, sequence: int, supported: bool = True) -> PlannedIntent:
    query = IntentRetrievalQuery(intent_id, heading, heading, heading, (heading,), None)
    source = _source(intent_id, f"I{sequence}-S1", chunk_id=sequence * 10)
    retrieval = IntentRetrievalResult(
        intent_id=intent_id,
        status="supported" if supported else "below_threshold",
        top_score=0.91 if supported else None,
        source_contexts=(source,) if supported else (),
        fallback_reason=None if supported else "insufficient_retrieval_confidence",
        has_unresolved_conflict=False,
        context_token_count=50 if supported else 0,
    )
    return PlannedIntent(sequence, intent_id, heading, query, retrieval)


def test_orchestrator_preserves_coverage_order_and_source_cards() -> None:
    plans = (_plan("ktp_el", "KTP Elektronik", 1), _plan("ikd", "IKD", 2, False))
    generated = GeneratedConversationAnswer(
        status="success",
        intent_answers=[
            GeneratedIntentAnswer(
                intent_id="ktp_el",
                status="success",
                answer="Pelayanan gratis dan selesai 1 hari kerja.",
                used_source_keys=["I1-S1"],
                needs_human_confirmation=False,
            )
        ],
    )
    sections, cards, status, reason = ResponseOrchestrator().build(plans=plans, generated=generated)
    assert [section.intent_id for section in sections] == ["ktp_el", "ikd"]
    assert [section.status for section in sections] == ["success", "insufficient_knowledge"]
    assert status == "success"
    assert reason == "partial_knowledge"
    assert len(cards) == 1
    assert cards[0].reference_label == "Halaman 2-3"


def test_orchestrator_all_fallback_has_no_sources() -> None:
    sections, cards, status, reason = ResponseOrchestrator().build(
        plans=(_plan("ktp_el", "KTP Elektronik", 1, False),), generated=None
    )
    assert status == "insufficient_knowledge"
    assert reason == "insufficient_retrieval_confidence"
    assert cards == ()
    assert "belum tersedia" in sections[0].body_markdown


def test_formatter_single_and_multi_heading() -> None:
    formatter = MarkdownFormatter()
    section = ResponseSection(1, "ktp_el", "KTP Elektronik", "success", "Isi.", ("I1-S1",), None)
    single = formatter.format(sections=(section,), greeting_text="Selamat pagi.", empathy_text=None)
    assert "## KTP Elektronik" in single
    assert "## 1." not in single
    multi = formatter.format(
        sections=(section, replace(section, sequence=2, intent_id="kia", heading="KIA")),
        greeting_text="Selamat siang.",
        empathy_text="Saya memahami situasinya.",
        overflow_count=1,
    )
    assert multi.startswith("Selamat siang. Saya memahami situasinya.")
    assert "## 1. KTP Elektronik" in multi
    assert "## 2. KIA" in multi
    assert "1 layanan tambahan" in multi


def test_markdown_sanitizer_removes_unsafe_content_and_source_keys() -> None:
    value = (
        "## KTP Elektronik\n<script>alert(1)</script>\n"
        "[x](bad)\n[tautan](javascript:x) I1-S1\n> Kutipan"
    )
    cleaned = sanitize_markdown(value, "KTP Elektronik")
    assert "script" not in cleaned
    assert "![" not in cleaned
    assert "javascript" not in cleaned
    assert "I1-S1" not in cleaned
    assert "Kutipan" in cleaned and ">" not in cleaned


@pytest.mark.parametrize(
    "answer",
    [
        "Biayanya Rp 25.000.",
        "Waktu penyelesaian 7 hari kerja.",
        "Berdasarkan Permendagri 999 Tahun 2099.",
        "Pelayanan ini gratis.",
    ],
)
def test_grounding_guard_rejects_unsupported_fee_time_or_regulation(answer: str) -> None:
    source = replace(_source("ktp_el", "I1-S1"), content="Syarat membawa dokumen resmi.")
    with pytest.raises(ValueError):
        validate_grounded_claims(answer, (source,))


def test_grounding_guard_accepts_supported_claims() -> None:
    validate_grounded_claims(
        "Pelayanan gratis, selesai 1 hari kerja berdasarkan Permendagri 108 Tahun 2019.",
        (_source("ktp_el", "I1-S1"),),
    )
