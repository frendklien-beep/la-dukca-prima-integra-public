from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.domain.conversation import (
    DetectedIntent,
    IntentDetectionResult,
    RecentMessage,
)

INTENT_REGISTRY: dict[str, dict[str, object]] = {
    "ktp_el": {
        "label": "KTP Elektronik",
        "aliases": (
            "kartu tanda penduduk",
            "kartu penduduk",
            "ktp elektronik",
            "e-ktp",
            "ektp",
            "ktp-el",
            "ktp",
            "identitas penduduk",
        ),
    },
    "kartu_keluarga": {
        "label": "Kartu Keluarga",
        "aliases": (
            "kartu keluarga",
            "pecah kk",
            "kk baru",
            "perubahan kk",
            "update kk",
            "masuk kk",
            "kk",
        ),
    },
    "akta_kelahiran": {
        "label": "Akta Kelahiran",
        "aliases": (
            "akta kelahiran",
            "akta lahir",
            "surat kelahiran",
            "pencatatan kelahiran",
            "kelahiran anak",
        ),
    },
    "akta_kematian": {
        "label": "Akta Kematian",
        "aliases": (
            "akta kematian",
            "surat kematian",
            "pencatatan kematian",
            "akta meninggal",
        ),
    },
    "kia": {
        "label": "Kartu Identitas Anak",
        "aliases": ("kartu identitas anak", "kartu anak", "kia"),
    },
    "ikd": {
        "label": "Identitas Kependudukan Digital",
        "aliases": ("identitas kependudukan digital", "ktp digital", "ikd"),
    },
    "pindah_datang": {
        "label": "Pindah Datang",
        "aliases": (
            "pindah datang",
            "datang penduduk",
            "masuk domisili",
            "pindah masuk",
        ),
    },
    "pindah_keluar": {
        "label": "Pindah Keluar",
        "aliases": (
            "pindah keluar",
            "surat pindah",
            "pindah domisili keluar",
            "pindah dari",
        ),
    },
    "perubahan_data": {
        "label": "Perubahan Data Kependudukan",
        "aliases": (
            "perubahan data",
            "ubah data",
            "perbaikan data",
            "koreksi data",
            "data salah",
            "nama salah",
            "perubahan nama",
            "perubahan biodata",
        ),
    },
    "akta_perkawinan": {
        "label": "Akta Perkawinan",
        "aliases": (
            "akta perkawinan",
            "catatan perkawinan",
            "pencatatan perkawinan",
            "nikah tercatat",
        ),
    },
    "akta_perceraian": {
        "label": "Akta Perceraian",
        "aliases": ("akta perceraian", "catatan perceraian", "pencatatan perceraian"),
    },
}

DOMAIN_TERMS = (
    "dukcapil",
    "administrasi kependudukan",
    "pencatatan sipil",
    "dokumen kependudukan",
    "dokumen identitas",
)

_REGIONAL_REPLACEMENTS = {
    "nyanda": "tidak",
    "nda": "tidak",
    "nggak": "tidak",
    "gak": "tidak",
    "mo": "mau",
    "ba urus": "mengurus",
    "urus ulang": "mengurus penggantian",
    "so": "sudah",
    "pe": "punya",
}
_SEGMENT_DELIMITER = re.compile(
    r"\s*(?:[,;]|/|&|\b(?:dan|serta|juga|lalu|kemudian|tapi|tetapi)\b)\s*",
    re.I,
)
_TOKEN = re.compile(r"[a-z0-9]+", re.I)


_SEMANTIC_RULES: tuple[tuple[str, re.Pattern[str], float, str], ...] = (
    (
        "ktp_el",
        re.compile(
            (
                r"\b(identitas|kartu penduduk)\b.{0,45}"
                r"\b(hilang|tidak ada|rusak|urus ulang|"
                r"penggantian)\b|"
                r"\b(belum punya|belum memiliki)\b.{0,35}"
                r"\b(identitas|kartu penduduk|ktp)\b"
            ),
            re.I,
        ),
        0.90,
        "identity_document_condition",
    ),
    (
        "kartu_keluarga",
        re.compile(
            (
                r"\b(anak|ayah|ibu|anggota keluarga)\b.{0,65}"
                r"\b(belum masuk|masih ada|hapus|"
                r"tambahkan)\b"
                r".{0,25}\b(keluarga|kk|kartu)\b|"
                r"\b(susunan|anggota)\s+keluarga\b"
            ),
            re.I,
        ),
        0.88,
        "family_composition_change",
    ),
    (
        "perubahan_data",
        re.compile(
            r"\b(nama|tanggal lahir|tempat lahir|biodata|data anak|data)\b"
            r".{0,45}\b(salah|keliru|beda|koreksi|perbaiki|ubah)\b|"
            r"\b(salah|keliru|beda)\b.{0,35}\b(nama|biodata|dokumen)\b",
            re.I,
        ),
        0.88,
        "biodata_correction",
    ),
    (
        "pindah_keluar",
        re.compile(
            r"\b(pindah tinggal|pindah rumah|pindah domisili)\b.{0,65}\b"
            r"(surat belum|belum urus|keluar|dari daerah|daerah lain)\b",
            re.I,
        ),
        0.83,
        "relocation_origin_process",
    ),
    (
        "pindah_datang",
        re.compile(
            r"\b(sekarang tinggal|sudah tinggal|pindah tinggal)\b.{0,45}\b"
            r"(tomohon|daerah tujuan|kota ini|masuk domisili)\b",
            re.I,
        ),
        0.82,
        "relocation_destination_process",
    ),
    (
        "akta_kematian",
        re.compile(
            r"\b(ayah|ibu|suami|istri|keluarga)\b.{0,45}\b(meninggal|wafat)\b|"
            r"\b(meninggal|wafat)\b.{0,50}\b(belum dicatat|belum ada akta|surat)\b",
            re.I,
        ),
        0.88,
        "death_life_event",
    ),
    (
        "akta_kelahiran",
        re.compile(
            r"\b(bayi|anak)\b.{0,45}\b(baru lahir|lahir|belum punya akta)\b|"
            r"\b(akan melahirkan|baru melahirkan)\b",
            re.I,
        ),
        0.84,
        "birth_life_event",
    ),
)


def normalize_intent_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for source, target in sorted(_REGIONAL_REPLACEMENTS.items(), key=lambda item: -len(item[0])):
        normalized = re.sub(rf"(?<!\w){re.escape(source)}(?!\w)", target, normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(normalize_intent_text(alias)).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.I)


_ALIAS_ENTRIES = sorted(
    (
        (normalize_intent_text(alias), intent_id, str(spec["label"]), _alias_pattern(alias))
        for intent_id, spec in INTENT_REGISTRY.items()
        for alias in spec["aliases"]
    ),
    key=lambda row: len(row[0]),
    reverse=True,
)


def _message_segments(message: str) -> tuple[tuple[int, int, str], ...]:
    segments: list[tuple[int, int, str]] = []
    cursor = 0
    for match in _SEGMENT_DELIMITER.finditer(message):
        raw = message[cursor : match.start()]
        value = raw.strip()
        if value:
            start = cursor + len(raw) - len(raw.lstrip())
            segments.append((start, match.start(), value))
        cursor = match.end()
    raw = message[cursor:]
    value = raw.strip()
    if value:
        start = cursor + len(raw) - len(raw.lstrip())
        segments.append((start, len(message), value))
    return tuple(segments) or ((0, len(message), message.strip()),)


def _segment_for(position: int, message: str) -> str:
    for start, end, segment in _message_segments(message):
        if start <= position <= end:
            return segment[:800]
    return message[:800]


def _find_aliases(message: str, normalized: str) -> list[tuple[int, DetectedIntent]]:
    found: list[tuple[int, DetectedIntent]] = []
    occupied: list[tuple[int, int]] = []
    for alias, intent_id, label, pattern in _ALIAS_ENTRIES:
        for match in pattern.finditer(normalized):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            occupied.append((match.start(), match.end()))
            found.append(
                (
                    match.start(),
                    DetectedIntent(
                        intent_id=intent_id,
                        canonical_label=label,
                        original_order=0,
                        segment=_segment_for(match.start(), message),
                        confidence=1.0,
                        detection_method="alias",
                        evidence=(f"alias:{alias}",),
                    ),
                )
            )
    return found


def _distinctive_lexical_match(alias: str, window: str) -> bool:
    generic = {"akta", "kartu", "pencatatan", "surat", "data", "dokumen"}
    alias_tokens = [token for token in _TOKEN.findall(alias) if token not in generic]
    window_tokens = [token for token in _TOKEN.findall(window) if token not in generic]
    if not alias_tokens:
        return True
    return all(
        any(
            SequenceMatcher(None, alias_token, window_token).ratio() >= 0.86
            for window_token in window_tokens
        )
        for alias_token in alias_tokens
    )


def _lexical_candidates(message: str, normalized: str) -> list[tuple[int, DetectedIntent]]:
    tokens = tuple(_TOKEN.findall(normalized))
    candidates: list[tuple[int, DetectedIntent]] = []
    windows = {normalized}
    for size in (1, 2, 3, 4):
        windows.update(
            " ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)
        )
    for intent_id, spec in INTENT_REGISTRY.items():
        best_score = 0.0
        best_alias = ""
        best_window = ""
        for alias_value in spec["aliases"]:
            alias = normalize_intent_text(str(alias_value))
            for window in windows:
                if not window:
                    continue
                score = SequenceMatcher(None, alias, window).ratio()
                if not _distinctive_lexical_match(alias, window):
                    continue
                if score > best_score:
                    best_score = score
                    best_alias = alias
                    best_window = window
        confident_threshold = 0.84 if len(best_alias) <= 4 else 0.78
        minimum_candidate = 0.62
        if best_score < minimum_candidate:
            continue
        position = normalized.find(best_window)
        candidates.append(
            (
                max(0, position),
                DetectedIntent(
                    intent_id=intent_id,
                    canonical_label=str(spec["label"]),
                    original_order=0,
                    segment=message[:800],
                    confidence=min(0.92, best_score),
                    detection_method="lexical",
                    evidence=(
                        f"similar_to:{best_alias}",
                        f"observed:{best_window}",
                        f"confidence_threshold:{confident_threshold}",
                    ),
                ),
            )
        )
    return candidates


def _semantic_candidates(message: str, normalized: str) -> list[tuple[int, DetectedIntent]]:
    candidates: list[tuple[int, DetectedIntent]] = []
    for intent_id, pattern, confidence, evidence in _SEMANTIC_RULES:
        match = pattern.search(normalized)
        if match is None:
            continue
        spec = INTENT_REGISTRY[intent_id]
        candidates.append(
            (
                match.start(),
                DetectedIntent(
                    intent_id=intent_id,
                    canonical_label=str(spec["label"]),
                    original_order=0,
                    segment=_segment_for(match.start(), message),
                    confidence=confidence,
                    detection_method="semantic",
                    evidence=(evidence, match.group(0)[:120]),
                ),
            )
        )
    return candidates


def _merge_candidates(
    candidates: list[tuple[int, DetectedIntent]],
) -> list[tuple[int, DetectedIntent]]:
    merged: dict[str, tuple[int, DetectedIntent]] = {}
    for position, candidate in sorted(candidates, key=lambda item: (item[0], -item[1].confidence)):
        existing = merged.get(candidate.intent_id)
        if existing is None:
            merged[candidate.intent_id] = (position, candidate)
            continue
        old_position, old = existing
        methods = {old.detection_method, candidate.detection_method}
        method = old.detection_method if len(methods) == 1 else "combined"
        confidence = min(
            1.0, max(old.confidence, candidate.confidence) + (0.04 if len(methods) > 1 else 0.0)
        )
        merged[candidate.intent_id] = (
            min(position, old_position),
            DetectedIntent(
                intent_id=old.intent_id,
                canonical_label=old.canonical_label,
                original_order=0,
                segment=old.segment if old_position <= position else candidate.segment,
                confidence=confidence,
                detection_method=method,
                evidence=tuple(dict.fromkeys((*old.evidence, *candidate.evidence))),
            ),
        )
    return sorted(merged.values(), key=lambda item: item[0])


def _recent_user_intents(recent_messages: tuple[RecentMessage, ...]) -> tuple[DetectedIntent, ...]:
    for recent in reversed(recent_messages):
        if recent.role != "user":
            continue
        result = detect_intents_detailed(recent.content, recent_messages=(), max_intents=5)
        if result.intents:
            return result.intents
    return ()


def detect_intents_detailed(
    message: str,
    *,
    recent_messages: tuple[RecentMessage, ...] = (),
    max_intents: int = 5,
) -> IntentDetectionResult:
    normalized = normalize_intent_text(message)
    candidates = _find_aliases(message, normalized)
    alias_intents = {candidate.intent_id for _, candidate in candidates}
    candidates.extend(
        item
        for item in _semantic_candidates(message, normalized)
        if item[1].intent_id not in alias_intents
    )
    semantic_intents = {candidate.intent_id for _, candidate in candidates}
    candidates.extend(
        item
        for item in _lexical_candidates(message, normalized)
        if item[1].intent_id not in semantic_intents
    )
    merged = _merge_candidates(candidates)

    if not merged and len(normalized) <= 120:
        prior = _recent_user_intents(recent_messages)
        if prior and re.search(
            r"\b(berapa|syarat|bagaimana|kalau|hilang|lama|biaya|dimana)\b", normalized
        ):
            inherited = prior[0]
            merged = [
                (
                    0,
                    DetectedIntent(
                        intent_id=inherited.intent_id,
                        canonical_label=inherited.canonical_label,
                        original_order=0,
                        segment=f"{message}\nKONTEKS TERBATAS: {inherited.segment}"[:800],
                        confidence=0.80,
                        detection_method="bounded_follow_up",
                        evidence=("safe_recent_user_intent", inherited.intent_id),
                    ),
                )
            ]

    low_confidence = tuple(candidate for _, candidate in merged if candidate.confidence < 0.72)
    confident = [
        (position, candidate) for position, candidate in merged if candidate.confidence >= 0.72
    ]

    is_domain = bool(confident or low_confidence) or any(
        term in normalized for term in DOMAIN_TERMS
    )
    if not confident and not low_confidence and any(term in normalized for term in DOMAIN_TERMS):
        confident = [
            (
                0,
                DetectedIntent(
                    intent_id="layanan_dukcapil_lainnya",
                    canonical_label="Layanan Dukcapil Lainnya",
                    original_order=0,
                    segment=message[:800],
                    confidence=0.75,
                    detection_method="semantic",
                    evidence=("generic_dukcapil_domain",),
                ),
            )
        ]

    overflow = max(0, len(confident) - max_intents)
    output = tuple(
        DetectedIntent(
            intent_id=candidate.intent_id,
            canonical_label=candidate.canonical_label,
            original_order=index,
            segment=candidate.segment,
            confidence=candidate.confidence,
            detection_method=candidate.detection_method,
            evidence=candidate.evidence,
        )
        for index, (_position, candidate) in enumerate(confident[:max_intents], start=1)
    )
    return IntentDetectionResult(
        intents=output,
        overflow_count=overflow,
        is_domain=is_domain,
        low_confidence_candidates=low_confidence,
        normalized_message=normalized,
    )


def detect_intents(
    message: str,
    *,
    recent_messages: tuple[RecentMessage, ...] = (),
    max_intents: int = 5,
) -> tuple[tuple[DetectedIntent, ...], int, bool]:
    """Backward-compatible wrapper for the original Sprint 5 call sites/tests."""
    result = detect_intents_detailed(
        message,
        recent_messages=recent_messages,
        max_intents=max_intents,
    )
    return result.intents, result.overflow_count, result.is_domain
