from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UrgencyAssessment:
    level: str
    evidence: tuple[str, ...]


_HIGH_TIME = (
    re.compile(r"\b(minggu depan|besok|hari ini|segera|mendesak|darurat)\b", re.I),
    re.compile(r"\b(sudah dekat waktunya|tinggal \d+\s*hari|dalam \d+\s*hari)\b", re.I),
)
_MEDIUM_TIME = (re.compile(r"\b(bulan ini|dalam waktu dekat|sebentar lagi|secepatnya)\b", re.I),)
_HIGH_CIRCUMSTANCE = (
    re.compile(r"\b(akan melahirkan|mau melahirkan|menjelang melahirkan)\b", re.I),
    re.compile(r"\b(bayi baru lahir|baru melahirkan)\b", re.I),
    re.compile(r"\b(baru meninggal|baru wafat)\b", re.I),
    re.compile(
        r"\b(dokumen|ktp|kk|akta)\b.{0,80}\b"
        r"(hilang|rusak|hangus|terbakar|hanyut|terendam|ditahan)\b",
        re.I,
    ),
)
_SERVICE_DEPENDENCY = re.compile(
    r"\b(dibutuhkan|diperlukan|syarat|untuk)\b.{0,100}\b"
    r"(rumah sakit|bpjs|sekolah|bank|layanan|pendaftaran|persalinan|pekerjaan|"
    r"bansos|pengadilan|waris|perjalanan)\b",
    re.I,
)
_OUT_OF_AREA = re.compile(
    r"\b(di luar daerah|beda daerah|daerah lain|luar kota|luar negeri|luar indonesia)\b",
    re.I,
)
_DISASTER_IMPACT = re.compile(
    r"\b(kebakaran|banjir|longsor|gempa|erupsi|bencana)\b.{0,100}\b"
    r"(mengungsi|evakuasi|rumah rusak|dokumen hilang|dokumen terbakar|hangus|hanyut)\b|"
    r"\b(mengungsi|evakuasi|dokumen hilang|dokumen terbakar|hangus|hanyut)\b.{0,100}\b"
    r"(kebakaran|banjir|longsor|gempa|erupsi|bencana)\b",
    re.I,
)
_HEALTH_RESTRICTION = re.compile(
    r"\b(dirawat|rawat inap|opname|sakit parah|kondisi kritis|terbaring|"
    r"tidak bisa datang|tidak dapat datang)\b",
    re.I,
)
_SAFETY_IMMEDIATE = re.compile(
    r"\b(sekarang dalam bahaya|sedang diancam|ancaman langsung|takut dibunuh|"
    r"melarikan diri dari kekerasan)\b",
    re.I,
)


class UrgencyDetector:
    """Classify administrative urgency without promising accelerated service."""

    def assess(self, message: str, *, context_tags: tuple[str, ...]) -> UrgencyAssessment:
        normalized = " ".join(message.split())
        evidence: list[str] = []
        high_time = any(pattern.search(normalized) for pattern in _HIGH_TIME)
        medium_time = any(pattern.search(normalized) for pattern in _MEDIUM_TIME)
        high_circumstance = any(pattern.search(normalized) for pattern in _HIGH_CIRCUMSTANCE)
        dependency = bool(_SERVICE_DEPENDENCY.search(normalized))
        out_of_area = bool(_OUT_OF_AREA.search(normalized))
        disaster_impact = bool(_DISASTER_IMPACT.search(normalized))
        health_restriction = bool(_HEALTH_RESTRICTION.search(normalized))
        safety_immediate = bool(_SAFETY_IMMEDIATE.search(normalized))

        if high_time:
            evidence.append("explicit_close_timeframe")
        if medium_time:
            evidence.append("important_timeframe")
        if high_circumstance:
            evidence.append("time_sensitive_life_event_or_document")
        if dependency:
            evidence.append("external_service_dependency")
        if out_of_area:
            evidence.append("different_domicile_or_out_of_area")
        if disaster_impact:
            evidence.append("disaster_with_material_impact")
        if health_restriction:
            evidence.append("health_or_attendance_restriction")
        if safety_immediate:
            evidence.append("immediate_safety_concern")

        tags = set(context_tags)
        imminent = "imminent_birth" in tags
        newborn = bool({"newborn_child", "recent_birth"}.intersection(tags))
        bereavement = "bereavement" in tags
        lost = "lost_identity_document" in tags
        multiple_lost = "multiple_documents_lost" in tags
        disaster = bool({"fire_incident", "disaster_affected"}.intersection(tags))
        displaced = bool({"evacuated", "displaced_resident"}.intersection(tags))
        severe_health = bool({"severe_illness", "hospitalized", "bedridden"}.intersection(tags))
        external_deadline = "time_sensitive_external_dependency" in tags

        # High urgency requires combined evidence, not a lone keyword or context tag.
        if safety_immediate:
            return UrgencyAssessment("high", tuple(dict.fromkeys(evidence)))
        if imminent and (high_time or high_circumstance):
            return UrgencyAssessment("high", tuple(dict.fromkeys((*evidence, "imminent_birth"))))
        if disaster and (multiple_lost or lost):
            return UrgencyAssessment(
                "high",
                tuple(dict.fromkeys((*evidence, "emergency_document_recovery"))),
            )
        if disaster and displaced and lost:
            return UrgencyAssessment(
                "high",
                tuple(dict.fromkeys((*evidence, "displaced_with_document_loss"))),
            )
        if severe_health and (dependency or high_time or external_deadline):
            return UrgencyAssessment(
                "high",
                tuple(dict.fromkeys((*evidence, "health_dependency"))),
            )
        if high_time and (high_circumstance or dependency or lost or bereavement):
            return UrgencyAssessment("high", tuple(dict.fromkeys(evidence)))
        if newborn and (dependency or high_time):
            return UrgencyAssessment(
                "high",
                tuple(dict.fromkeys((*evidence, "newborn_dependency"))),
            )
        if out_of_area and high_time and dependency:
            return UrgencyAssessment("high", tuple(dict.fromkeys(evidence)))
        if external_deadline and (dependency or lost):
            return UrgencyAssessment("high", tuple(dict.fromkeys(evidence)))

        if (
            high_time
            or medium_time
            or high_circumstance
            or dependency
            or out_of_area
            or disaster
            or displaced
            or severe_health
            or health_restriction
        ):
            return UrgencyAssessment("medium", tuple(dict.fromkeys(evidence)))
        return UrgencyAssessment("normal", ())
