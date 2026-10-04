from __future__ import annotations

import re
from dataclasses import replace

from app.domain.conversation import (
    DetectedIntent,
    HumanContext,
    PlannedIntent,
    ServiceRelationshipPlan,
)
from app.services.conversation.intents import INTENT_REGISTRY

_LABELS = {intent_id: str(spec["label"]) for intent_id, spec in INTENT_REGISTRY.items()}


_LIFE_EVENT_RELATIONS: dict[str, tuple[str, ...]] = {
    "pregnancy": ("akta_kelahiran", "kartu_keluarga"),
    "imminent_birth": ("akta_kelahiran", "kartu_keluarga"),
    "recent_birth": ("akta_kelahiran", "kartu_keluarga", "kia"),
    "newborn_child": ("akta_kelahiran", "kartu_keluarga", "kia"),
    "bereavement": ("akta_kematian", "kartu_keluarga"),
    "different_domicile": ("pindah_keluar", "pindah_datang", "kartu_keluarga", "ktp_el"),
    "lost_identity_document": ("ktp_el",),
    "birth_document_pending": ("akta_kelahiran", "kartu_keluarga"),
    "deceased_still_in_family_record": ("akta_kematian", "kartu_keluarga"),
    "family_record_mismatch": ("kartu_keluarga",),
    "identity_data_mismatch": ("perubahan_data",),
    "biodata_conflict": ("perubahan_data",),
    "unregistered_marriage": ("akta_perkawinan", "kartu_keluarga"),
}


def _label(intent_id: str) -> str:
    return _LABELS.get(intent_id, intent_id.replace("_", " ").title())


class ServiceDependencyPlanner:
    """Plan relationships as possibilities until Knowledge Base evidence confirms them."""

    def build_initial(
        self,
        *,
        intents: tuple[DetectedIntent, ...],
        human_context: HumanContext,
    ) -> ServiceRelationshipPlan:
        explicit_ids = tuple(dict.fromkeys(item.intent_id for item in intents))
        related_ids: list[str] = []
        notes: list[str] = []
        for tag in human_context.tags:
            for candidate in _LIFE_EVENT_RELATIONS.get(tag, ()):
                if candidate not in explicit_ids and candidate not in related_ids:
                    related_ids.append(candidate)
                    notes.append(f"possible_relation:{tag}->{candidate}")

        recommended_ids = list(explicit_ids)
        if human_context.priority_hints:
            rank = {value: index for index, value in enumerate(human_context.priority_hints)}
            recommended_ids.sort(key=lambda value: rank.get(value, len(rank)))

        requires_verification = human_context.requires_human_verification or any(
            tag in human_context.tags
            for tag in (
                "unregistered_marriage",
                "different_domicile",
                "multiple_sensitive_circumstances",
                "manual_verification_required",
                "guardian_context",
                "institutionalized",
                "safety_risk",
                "no_fixed_address",
            )
        )
        confidence = 0.75 if related_ids else (1.0 if explicit_ids else 0.0)
        return ServiceRelationshipPlan(
            explicit_services=tuple(_label(value) for value in explicit_ids),
            related_services=tuple(_label(value) for value in related_ids),
            prerequisites=(),
            optional_follow_ups=tuple(_label(value) for value in related_ids),
            recommended_order=tuple(_label(value) for value in recommended_ids),
            parallel_possible=(),
            dependency_confidence=confidence,
            requires_human_verification=requires_verification,
            evidence_notes=tuple(notes),
        )

    def finalize(
        self,
        *,
        initial: ServiceRelationshipPlan,
        plans: tuple[PlannedIntent, ...],
    ) -> ServiceRelationshipPlan:
        prerequisites: list[str] = []
        evidence_notes = list(initial.evidence_notes)
        supported_labels: list[str] = []
        for plan in plans:
            retrieval = plan.retrieval
            if retrieval is None or retrieval.status != "supported":
                continue
            supported_labels.append(plan.heading)
            source_text = "\n".join(
                source.content for source in retrieval.source_contexts
            ).casefold()
            for candidate_id, candidate_label in _LABELS.items():
                if candidate_label.casefold() == plan.heading.casefold():
                    continue
                aliases = tuple(
                    str(alias).casefold()
                    for alias in INTENT_REGISTRY.get(candidate_id, {}).get("aliases", ())
                )
                if not any(alias in source_text for alias in aliases):
                    continue
                alias_pattern = "|".join(re.escape(alias) for alias in aliases if alias)
                if not alias_pattern:
                    continue
                obligation_pattern = r"harus|wajib|terlebih dahulu|prasyarat|persyaratan"
                mandatory_pattern = re.compile(
                    rf"(?:\b(?:{obligation_pattern})\b.{{0,120}}\b(?:{alias_pattern})\b"
                    rf"|\b(?:{alias_pattern})\b.{{0,120}}\b(?:{obligation_pattern})\b)",
                    re.I,
                )
                if mandatory_pattern.search(source_text):
                    label = _label(candidate_id)
                    if label not in prerequisites:
                        prerequisites.append(label)
                        evidence_notes.append(
                            f"kb_supported_prerequisite:{plan.intent_id}->{candidate_id}"
                        )

        recommended = list(initial.recommended_order)
        for prerequisite in reversed(prerequisites):
            if prerequisite in recommended:
                recommended.remove(prerequisite)
            recommended.insert(0, prerequisite)

        parallel: list[tuple[str, ...]] = []
        if len(supported_labels) > 1 and not prerequisites:
            parallel.append(tuple(supported_labels))

        return replace(
            initial,
            prerequisites=tuple(prerequisites),
            recommended_order=tuple(dict.fromkeys(recommended)),
            parallel_possible=tuple(parallel),
            dependency_confidence=(0.95 if prerequisites else initial.dependency_confidence),
            evidence_notes=tuple(dict.fromkeys(evidence_notes)),
        )
