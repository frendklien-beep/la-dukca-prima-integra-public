from __future__ import annotations

import re

from app.domain.conversation import (
    ClaimAssessment,
    GroundingValidationResult,
    ResponseSection,
    SourceContext,
)
from app.schemas.generated_chat import GeneratedClaim

_HTML = re.compile(r"<[^>]+>")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_SOURCE_KEY = re.compile(r"\bI\d+-S\d+\b")
_SCRIPT = re.compile(r"(?is)<\s*(script|iframe)[^>]*>.*?<\s*/\s*\1\s*>")
_REGULATION = re.compile(
    r"\b(undang-undang|uu|pp|perpres|permendagri|perda|perwako)\s*"
    r"(?:nomor\s*)?(\d+)\s*(?:tahun\s*)?(\d{4})\b",
    re.I,
)
_AMOUNT = re.compile(r"\bRp\.?\s*[0-9][0-9.,]*", re.I)
_DURATION = re.compile(r"\b\d+\s*(?:hari kerja|hari|jam|menit)\b", re.I)
_TOKEN = re.compile(r"[a-z0-9]+", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+(?=(?:[-*]|\d+[.)])\s+)")
_FORBIDDEN_CLAIMS = (
    "saya sudah mengecek nik anda",
    "permohonan anda pasti disetujui",
    "data anda sudah terdaftar",
    "permohonan anda sudah ditolak",
    "permohonan anda pasti selesai",
)
_IMPORTANT_MARKERS = re.compile(
    r"\b(wajib|harus|persyaratan|syarat|membawa|melampirkan|terlebih dahulu|"
    r"hanya dapat|berhak|tidak dapat|dilakukan di|datang ke|gratis|biaya|"
    r"hari kerja|jam|menit|berdasarkan|sesuai|prasyarat|digabung|bersamaan)\b",
    re.I,
)
_MANDATORY_MARKERS = re.compile(
    r"\b(wajib|harus|terlebih dahulu|prasyarat|hanya dapat|tidak dapat|"
    r"membawa|melampirkan)\b",
    re.I,
)

_SOURCE_LIMITATION_MARKERS = re.compile(
    r"(?:"
    r"\b(?:sumber|dokumen acuan|informasi|knowledge\s*base)\b.{0,180}"
    r"\b(?:tidak|belum)\b.{0,60}"
    r"\b(?:memuat|mencantumkan|menjelaskan|menyediakan|berisi)\b"
    r"|"
    r"\b(?:tidak|belum)\b.{0,60}"
    r"\b(?:tersedia|ditemukan|tercantum|dijelaskan)\b.{0,120}"
    r"\b(?:dalam|pada)\b.{0,40}"
    r"\b(?:sumber|dokumen acuan|knowledge\s*base)\b"
    r")",
    re.I | re.S,
)
_INFERENCE_MARKERS = re.compile(
    r"\b(mungkin|dapat menjadi|dapat berkaitan|perlu diperiksa|"
    r"berdasarkan gabungan sumber|dapat dikonfirmasi|kemungkinan)\b",
    re.I,
)
_STOPWORDS = {
    "yang",
    "dan",
    "atau",
    "untuk",
    "dengan",
    "dari",
    "pada",
    "ini",
    "itu",
    "anda",
    "dapat",
    "perlu",
    "harus",
    "wajib",
    "adalah",
    "sebagai",
}


def sanitize_markdown(value: str, heading: str) -> str:
    text = value.strip()
    text = _SCRIPT.sub("", text)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _HTML.sub("", text)
    text = _SOURCE_KEY.sub("", text)
    lines = [
        line[1:].lstrip() if line.lstrip().startswith(">") else line for line in text.splitlines()
    ]
    if lines and lines[0].strip().casefold() in {
        f"## {heading}".casefold(),
        f"### {heading}".casefold(),
        heading.casefold(),
    }:
        lines = lines[1:]
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        raise ValueError("Bagian jawaban kosong setelah sanitasi.")
    lowered = text.casefold()
    if any(claim in lowered for claim in _FORBIDDEN_CLAIMS):
        raise ValueError("Jawaban mengandung klaim yang tidak diizinkan.")
    return text


def _claim_key(match: re.Match[str]) -> tuple[str, str, str]:
    return (match.group(1).casefold(), match.group(2), match.group(3))


def _terms(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN.findall(value)
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    }


def _important_claims(answer: str) -> tuple[str, ...]:
    claims: list[str] = []
    for segment in _SENTENCE.split(answer):
        value = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", segment).strip()
        if value and (
            _IMPORTANT_MARKERS.search(value)
            or _REGULATION.search(value)
            or _AMOUNT.search(value)
            or _DURATION.search(value)
        ):
            claims.append(value)
    return tuple(dict.fromkeys(claims))


def _sanitize_unsupported_claims(
    answer: str,
    unsupported: tuple[ClaimAssessment, ...],
) -> str:
    sanitized = answer

    for item in unsupported:
        if item.text:
            sanitized = sanitized.replace(item.text, "", 1)

    empty_list_item = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*$")
    lines = [
        line.rstrip() for line in sanitized.splitlines() if not empty_list_item.fullmatch(line)
    ]

    sanitized = "\n".join(lines).strip()
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    return sanitized


def _exact_sensitive_checks(claim: str, source_text: str) -> bool:
    source_regulations = {_claim_key(match) for match in _REGULATION.finditer(source_text)}
    if any(_claim_key(match) not in source_regulations for match in _REGULATION.finditer(claim)):
        return False
    normalized_sources = re.sub(r"\s+", "", source_text.casefold())
    for match in _AMOUNT.finditer(claim):
        if re.sub(r"\s+", "", match.group(0)).casefold() not in normalized_sources:
            return False
    for match in _DURATION.finditer(claim):
        if match.group(0).casefold() not in source_text.casefold():
            return False
    if "gratis" in claim.casefold() and "gratis" not in source_text.casefold():
        return False
    return True


def _classify_claim(claim: str, sources: tuple[SourceContext, ...]) -> ClaimAssessment:
    source_texts = {
        source.source_key: f"{source.title} {source.section_title or ''} {source.content}"
        for source in sources
    }
    combined = "\n".join(source_texts.values())
    if not _exact_sensitive_checks(claim, combined):
        return ClaimAssessment(claim, "unsupported", (), 0.0)

    claim_terms = _terms(claim)

    # Sebuah klaim dapat didukung oleh beberapa potongan sumber sekaligus.
    combined_terms = _terms(combined)
    combined_overlap = len(claim_terms & combined_terms) / max(
        1,
        len(claim_terms),
    )

    ranked: list[tuple[float, str]] = []
    for key, text in source_texts.items():
        source_terms = _terms(text)
        overlap = len(claim_terms & source_terms) / max(1, len(claim_terms))
        ranked.append((overlap, key))

    ranked.sort(reverse=True)

    top = ranked[0][0] if ranked else 0.0
    used = tuple(key for score, key in ranked if score >= max(0.30, top - 0.12))[:5]

    grounding_overlap = max(top, combined_overlap)

    if grounding_overlap >= 0.62 or claim.casefold() in combined.casefold():
        return ClaimAssessment(
            claim,
            "supported",
            used,
            min(1.0, 0.55 + grounding_overlap * 0.45),
        )
    if len(sources) >= 2 and top >= 0.35 and _INFERENCE_MARKERS.search(claim):
        return ClaimAssessment(claim, "inferred", used, min(0.85, 0.40 + top))
    return ClaimAssessment(claim, "unsupported", used, top)


def _is_unsupported_mandatory_claim(item: ClaimAssessment) -> bool:
    if not _MANDATORY_MARKERS.search(item.text):
        return False

    if _SOURCE_LIMITATION_MARKERS.search(item.text):
        return False

    return True


def assess_claim_grounding(
    answer: str,
    sources: tuple[SourceContext, ...],
    declared_claims: tuple[GeneratedClaim, ...] = (),
) -> GroundingValidationResult:
    assessments = tuple(_classify_claim(claim, sources) for claim in _important_claims(answer))
    unsupported = tuple(item for item in assessments if item.status == "unsupported")

    allowed_keys = {source.source_key for source in sources}
    for declared in declared_claims:
        if not set(declared.source_keys).issubset(allowed_keys):
            unsupported += (ClaimAssessment(declared.text, "unsupported", (), 0.0),)
        if declared.status == "unsupported":
            unsupported += (
                ClaimAssessment(
                    declared.text,
                    "unsupported",
                    tuple(declared.source_keys),
                    declared.confidence,
                ),
            )

    mandatory_unsupported = tuple(
        item for item in unsupported if _is_unsupported_mandatory_claim(item)
    )

    if mandatory_unsupported:
        diagnostic_items = "; ".join(
            (
                f"claim={item.text[:300]!r}, "
                f"confidence={item.confidence:.3f}, "
                f"source_keys={list(item.source_keys)}"
            )
            for item in mandatory_unsupported[:5]
        )

        raise ValueError(
            "Jawaban memuat instruksi wajib yang tidak didukung sumber. "
            f"Details: {diagnostic_items}"
        )
    sanitized_answer = _sanitize_unsupported_claims(answer, unsupported)

    if unsupported and not sanitized_answer:
        raise ValueError("Tidak ada bagian jawaban yang aman setelah klaim tidak didukung dibuang.")
    if unsupported:
        status = "warning"
    else:
        status = "passed"
    return GroundingValidationResult(
        claims=assessments,
        unsupported_claims_detected=bool(unsupported),
        grounding_status=status,
        sanitized_answer=sanitized_answer,
    )


def validate_grounded_claims(answer: str, sources: tuple[SourceContext, ...]) -> None:
    result = assess_claim_grounding(answer, sources)
    if result.unsupported_claims_detected:
        raise ValueError("Klaim penting tidak cukup didukung sumber yang digunakan.")


def validate_section_sources(
    section: ResponseSection,
    source_map: dict[str, SourceContext],
) -> GroundingValidationResult | None:
    if section.status == "success" and not section.source_keys:
        raise ValueError("Bagian sukses wajib memiliki sumber.")
    used: list[SourceContext] = []
    for key in section.source_keys:
        source = source_map.get(key)
        if source is None or source.intent_id != section.intent_id:
            raise ValueError("Sumber tidak valid atau lintas intent.")
        used.append(source)
    if section.status == "success":
        return assess_claim_grounding(section.body_markdown, tuple(used))
    return None
