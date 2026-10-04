from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date

from app.domain.conversation import SourceContext


@dataclass(frozen=True, slots=True)
class RegulatoryMetadata:
    document_type: str
    number: str
    year: int | None
    title: str
    authority_rank: int | None
    jurisdiction: str
    effective_date: date | None
    status: str
    amends: tuple[str, ...]
    amended_by: tuple[str, ...]
    revokes: tuple[str, ...]
    revoked_by: tuple[str, ...]
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegulatoryResolution:
    sources: tuple[SourceContext, ...]
    excluded_document_ids: tuple[int, ...]
    conflicts: tuple[str, ...]
    requires_human_verification: bool

    def diagnostic_summary(self) -> dict[str, object]:
        return {
            "active_sources": [
                source.source_key or str(source.document_id) for source in self.sources
            ],
            "excluded_sources": list(self.excluded_document_ids),
            "conflicts": list(self.conflicts),
            "requires_human_verification": self.requires_human_verification,
        }


def parse_relationships(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError, TypeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(
        str(item).strip() for item in parsed if isinstance(item, (str, int)) and str(item).strip()
    )


def document_identifier(source: SourceContext) -> str:
    if source.document_number and source.document_year:
        return f"{source.document_number}/{source.document_year}".casefold()
    if source.document_number:
        return source.document_number.casefold()
    return source.title.casefold()


def _is_regulatory(source: SourceContext) -> bool:
    value = (source.document_type or source.category or "").casefold()
    return value in {
        "regulation",
        "peraturan",
        "undang_undang",
        "permendagri",
        "perda",
        "perwako",
    }


def _jurisdiction_applicable(jurisdiction: str, target: str) -> bool:
    current = jurisdiction.casefold().strip()
    requested = target.casefold().strip()
    if current in {"", "unknown", "national", "indonesia"}:
        return True
    if requested in {"", "unknown"}:
        return current in {"city", "local", "tomohon", "kota tomohon"}
    if requested in current or current in requested:
        return True
    if current in {"city", "local"} and requested in {"tomohon", "kota tomohon"}:
        return True
    return False


class RegulatoryResolver:
    """Practical backend resolution, not autonomous legal reasoning."""

    def resolve(
        self,
        sources: tuple[SourceContext, ...],
        *,
        target_jurisdiction: str = "tomohon",
    ) -> RegulatoryResolution:
        identifiers = {document_identifier(source): source for source in sources}
        excluded: set[int] = set()
        conflicts: list[str] = []
        resolved: list[SourceContext] = []

        for source in sources:
            status = (source.legal_status or "unknown").casefold()
            warnings = list(source.regulatory_warnings)
            if status == "revoked":
                excluded.add(source.document_id)
                continue
            if source.revoked_by:
                active_revoker = next(
                    (
                        identifiers.get(reference.casefold())
                        for reference in source.revoked_by
                        if identifiers.get(reference.casefold()) is not None
                    ),
                    None,
                )
                if active_revoker and (active_revoker.legal_status or "unknown") != "revoked":
                    excluded.add(source.document_id)
                    continue
                warnings.append("revocation_requires_verification")

            score = source.score
            if status == "superseded":
                score -= 0.15
                warnings.append("superseded_source_deprioritized")
            elif status == "amended":
                score -= 0.04
                warnings.append("amended_source_reviewed_with_amendment")
            elif status == "unknown" and _is_regulatory(source):
                score -= 0.03
                warnings.append("regulatory_validity_unknown")

            if not _jurisdiction_applicable(source.jurisdiction, target_jurisdiction):
                score -= 0.25
                warnings.append("jurisdiction_mismatch")

            resolved.append(
                replace(
                    source,
                    score=max(-1.0, score),
                    regulatory_warnings=tuple(dict.fromkeys(warnings)),
                )
            )

        # Explicit relationship conflicts are deterministic; the model never decides them.
        by_identifier = {document_identifier(source): source for source in resolved}
        for source in resolved:
            source_id = document_identifier(source)
            for reference in source.revokes:
                target = by_identifier.get(reference.casefold())
                if target and target.document_id not in excluded:
                    excluded.add(target.document_id)
            for reference in source.amends:
                target = by_identifier.get(reference.casefold())
                if target and target.effective_date and source.effective_date:
                    if source.effective_date < target.effective_date:
                        conflicts.append(
                            f"amendment_date_conflict:{source_id}:{document_identifier(target)}"
                        )

        resolved = [source for source in resolved if source.document_id not in excluded]
        regulatory_sources = [source for source in resolved if _is_regulatory(source)]
        unknown_validity = any(
            (source.legal_status or "unknown").casefold() == "unknown"
            or "regulatory_validity_unknown" in source.regulatory_warnings
            for source in regulatory_sources
        )
        jurisdiction_uncertain = any(
            "jurisdiction_mismatch" in source.regulatory_warnings for source in regulatory_sources
        )
        return RegulatoryResolution(
            sources=tuple(resolved),
            excluded_document_ids=tuple(sorted(excluded)),
            conflicts=tuple(dict.fromkeys(conflicts)),
            requires_human_verification=bool(
                conflicts or unknown_validity or jurisdiction_uncertain
            ),
        )
