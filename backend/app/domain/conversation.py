from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecentMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class HumanContext:
    tags: tuple[str, ...]
    sensitivity: str
    urgency: str
    empathy_mode: str
    empathy_text: str | None
    priority_hints: tuple[str, ...]
    response_guidance: tuple[str, ...]
    privacy_risk: str = "low"
    requires_clarification: bool = False
    clarification_reasons: tuple[str, ...] = ()
    accessibility_needs: tuple[str, ...] = ()
    safety_flags: tuple[str, ...] = ()
    requires_human_verification: bool = False

    @property
    def context_tags(self) -> tuple[str, ...]:
        """Normalized remediation name while preserving the Sprint 5 public object."""
        return self.tags

    def diagnostic_summary(self) -> dict[str, object]:
        return {
            "context_tags": list(self.tags),
            "empathy_mode": self.empathy_mode,
            "urgency": self.urgency,
            "priority_hints": list(self.priority_hints),
            "privacy_risk": self.privacy_risk,
            "accessibility_needs": list(self.accessibility_needs),
            "safety_flags": list(self.safety_flags),
            "requires_clarification": self.requires_clarification,
            "clarification_reasons": list(self.clarification_reasons),
            "requires_human_verification": self.requires_human_verification,
        }


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    session_id: UUID
    is_new_session: bool
    greeting_already_sent: bool
    safe_message: str
    recent_messages: tuple[RecentMessage, ...]
    now_utc: datetime


@dataclass(frozen=True, slots=True)
class DetectedIntent:
    intent_id: str
    canonical_label: str
    original_order: int
    segment: str
    confidence: float
    detection_method: str
    evidence: tuple[str, ...] = ()

    def diagnostic_summary(self) -> dict[str, object]:
        method = self.detection_method
        if method not in {"alias", "lexical", "semantic", "combined"}:
            method = "combined"
        return {
            "intent": self.intent_id,
            "confidence": round(self.confidence, 4),
            "detection_method": method,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class IntentDetectionResult:
    intents: tuple[DetectedIntent, ...]
    overflow_count: int
    is_domain: bool
    low_confidence_candidates: tuple[DetectedIntent, ...] = ()
    normalized_message: str = ""


@dataclass(frozen=True, slots=True)
class ClarificationPlan:
    needs_clarification: bool
    missing_information: tuple[str, ...]
    questions: tuple[str, ...]
    reason: str
    blocks_generation: bool = False

    @classmethod
    def none(cls) -> ClarificationPlan:
        return cls(False, (), (), "", False)

    def diagnostic_summary(self) -> dict[str, object]:
        return {
            "needs_clarification": self.needs_clarification,
            "missing_information": list(self.missing_information),
            "questions": list(self.questions),
            "reason": self.reason,
            "blocks_generation": self.blocks_generation,
        }


@dataclass(frozen=True, slots=True)
class ServiceRelationshipPlan:
    explicit_services: tuple[str, ...]
    related_services: tuple[str, ...]
    prerequisites: tuple[str, ...]
    optional_follow_ups: tuple[str, ...]
    recommended_order: tuple[str, ...]
    parallel_possible: tuple[tuple[str, ...], ...]
    dependency_confidence: float
    requires_human_verification: bool
    evidence_notes: tuple[str, ...] = ()

    @classmethod
    def empty(cls, explicit_services: tuple[str, ...] = ()) -> ServiceRelationshipPlan:
        return cls(explicit_services, (), (), (), explicit_services, (), 0.0, False, ())

    def diagnostic_summary(self) -> dict[str, object]:
        return {
            "explicit_services": list(self.explicit_services),
            "related_services": list(self.related_services),
            "prerequisites": list(self.prerequisites),
            "optional_follow_ups": list(self.optional_follow_ups),
            "recommended_order": list(self.recommended_order),
            "parallel_possible": [list(item) for item in self.parallel_possible],
            "dependency_confidence": round(self.dependency_confidence, 4),
            "requires_human_verification": self.requires_human_verification,
        }


@dataclass(frozen=True, slots=True)
class ConversationPlan:
    intents: tuple[DetectedIntent, ...]
    human_context: HumanContext
    greeting_text: str | None
    empathy_text: str | None
    empathy_mode: str
    is_out_of_scope: bool
    needs_clarification: bool
    overflow_count: int = 0
    prompt_injection_signal: bool = False
    clarification: ClarificationPlan = field(default_factory=ClarificationPlan.none)
    service_plan: ServiceRelationshipPlan = field(default_factory=ServiceRelationshipPlan.empty)


@dataclass(frozen=True, slots=True)
class IntentRetrievalQuery:
    intent_id: str
    canonical_label: str
    original_segment: str
    normalized_query: str
    service_terms: tuple[str, ...]
    allowed_categories: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class SourceContext:
    source_key: str
    intent_id: str
    document_id: int
    chunk_id: int
    title: str
    category: str
    authority_rank: int
    jurisdiction: str
    effective_date: date | None
    page_start: int | None
    page_end: int | None
    section_title: str | None
    content: str
    score: float
    document_type: str | None = None
    document_number: str | None = None
    document_year: int | None = None
    legal_status: str | None = None
    issuer: str | None = None
    amends: tuple[str, ...] = ()
    amended_by: tuple[str, ...] = ()
    revokes: tuple[str, ...] = ()
    revoked_by: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    regulatory_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntentRetrievalResult:
    intent_id: str
    status: str
    top_score: float | None
    source_contexts: tuple[SourceContext, ...]
    fallback_reason: str | None
    has_unresolved_conflict: bool
    context_token_count: int
    excluded_source_ids: tuple[int, ...] = ()
    regulatory_conflicts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlannedIntent:
    sequence: int
    intent_id: str
    heading: str
    query: IntentRetrievalQuery
    retrieval: IntentRetrievalResult | None = None


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    text: str
    status: str
    source_keys: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class GroundingValidationResult:
    claims: tuple[ClaimAssessment, ...]
    unsupported_claims_detected: bool
    grounding_status: str
    sanitized_answer: str

    def diagnostic_summary(self) -> dict[str, object]:
        return {
            "claims": [
                {
                    "text": item.text[:240],
                    "status": item.status,
                    "source_keys": list(item.source_keys),
                    "confidence": round(item.confidence, 4),
                }
                for item in self.claims
            ],
            "unsupported_claims_detected": self.unsupported_claims_detected,
            "grounding_status": self.grounding_status,
        }


@dataclass(frozen=True, slots=True)
class ResponseSection:
    sequence: int
    intent_id: str
    heading: str
    status: str
    body_markdown: str
    source_keys: tuple[str, ...]
    fallback_reason: str | None
    grounding: GroundingValidationResult | None = None


@dataclass(frozen=True, slots=True)
class SourceCard:
    document_id: int
    chunk_id: int
    title: str
    page_start: int | None
    page_end: int | None
    section: str | None
    reference_label: str
    relevance_score: float


@dataclass(frozen=True, slots=True)
class GenerationDiagnostics:
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    attempts: int
    provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChatServiceResult:
    session_id: UUID
    message_id: int
    status: str
    answer: str
    sources: tuple[SourceCard, ...]
    fallback_reason: str | None
    privacy_notice: str
