from __future__ import annotations

from app.domain.conversation import DetectedIntent, IntentRetrievalQuery, PlannedIntent
from app.services.conversation.intents import INTENT_REGISTRY


class KnowledgePlanner:
    def build(self, intents: tuple[DetectedIntent, ...]) -> tuple[PlannedIntent, ...]:
        planned: list[PlannedIntent] = []
        for sequence, intent in enumerate(intents, start=1):
            aliases = tuple(
                str(alias) for alias in INTENT_REGISTRY.get(intent.intent_id, {}).get("aliases", ())
            )
            normalized_query = f"LAYANAN: {intent.canonical_label}\nPERTANYAAN: {intent.segment}"
            planned.append(
                PlannedIntent(
                    sequence=sequence,
                    intent_id=intent.intent_id,
                    heading=intent.canonical_label,
                    query=IntentRetrievalQuery(
                        intent_id=intent.intent_id,
                        canonical_label=intent.canonical_label,
                        original_segment=intent.segment,
                        normalized_query=normalized_query,
                        service_terms=aliases or (intent.canonical_label,),
                        allowed_categories=None,
                    ),
                )
            )
        return tuple(planned)
