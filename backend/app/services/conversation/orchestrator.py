from __future__ import annotations

from app.domain.conversation import PlannedIntent, ResponseSection, SourceCard, SourceContext
from app.schemas.generated_chat import GeneratedConversationAnswer
from app.services.conversation.validation import sanitize_markdown, validate_section_sources

FALLBACK_BODY = (
    "Informasi untuk layanan ini belum tersedia atau belum cukup jelas dalam Knowledge Base "
    "resmi yang aktif. Silakan menghubungi petugas Dinas Dukcapil Kota Tomohon untuk "
    "memperoleh konfirmasi."
)
REGULATORY_FALLBACK_BODY = (
    "Sumber yang tersedia memerlukan verifikasi lebih lanjut terkait keberlakuan, perubahan, "
    "atau yurisdiksinya. Saya tidak akan memilih salah satu ketentuan secara sepihak. "
    "Silakan konfirmasikan kepada petugas berwenang dengan menyebutkan sumber yang tercantum."
)
SOURCE_CONFLICT_BODY = (
    "Terdapat perbedaan yang belum dapat diselesaikan secara aman pada sumber resmi yang "
    "tersedia. Mohon verifikasi kepada petugas berwenang; saya tidak akan menentukan sendiri "
    "ketentuan mana yang berlaku."
)


class ResponseOrchestrator:
    def build(
        self,
        *,
        plans: tuple[PlannedIntent, ...],
        generated: GeneratedConversationAnswer | None,
    ) -> tuple[tuple[ResponseSection, ...], tuple[SourceCard, ...], str, str | None]:
        generated_map = {
            answer.intent_id: answer for answer in (generated.intent_answers if generated else [])
        }
        sections: list[ResponseSection] = []
        source_map: dict[str, SourceContext] = {}
        for plan in plans:
            if plan.retrieval:
                for source in plan.retrieval.source_contexts:
                    source_map[source.source_key] = source

            answer = generated_map.get(plan.intent_id)
            if (
                plan.retrieval
                and plan.retrieval.status == "supported"
                and answer
                and answer.status == "success"
            ):
                section = ResponseSection(
                    sequence=plan.sequence,
                    intent_id=plan.intent_id,
                    heading=plan.heading,
                    status="success",
                    body_markdown=sanitize_markdown(answer.answer, plan.heading),
                    source_keys=tuple(answer.used_source_keys),
                    fallback_reason=None,
                )
                grounding = validate_section_sources(section, source_map)
                section = ResponseSection(
                    sequence=section.sequence,
                    intent_id=section.intent_id,
                    heading=section.heading,
                    status=section.status,
                    body_markdown=section.body_markdown,
                    source_keys=section.source_keys,
                    fallback_reason=section.fallback_reason,
                    grounding=grounding,
                )
            else:
                reason = (
                    plan.retrieval.fallback_reason
                    if plan.retrieval and plan.retrieval.fallback_reason
                    else "no_relevant_source"
                )
                source_keys: tuple[str, ...] = ()
                body = FALLBACK_BODY
                if plan.retrieval and plan.retrieval.status == "conflict":
                    source_keys = tuple(
                        source.source_key for source in plan.retrieval.source_contexts
                    )
                    body = (
                        REGULATORY_FALLBACK_BODY
                        if reason == "regulatory_verification_required"
                        else SOURCE_CONFLICT_BODY
                    )
                section = ResponseSection(
                    sequence=plan.sequence,
                    intent_id=plan.intent_id,
                    heading=plan.heading,
                    status="insufficient_knowledge",
                    body_markdown=body,
                    source_keys=source_keys,
                    fallback_reason=reason,
                )
            sections.append(section)

        successful = [section for section in sections if section.status == "success"]
        if len(successful) == len(sections) and sections:
            public_status = "success"
            fallback_reason = None
        elif successful:
            public_status = "success"
            fallback_reason = "partial_knowledge"
        else:
            public_status = "insufficient_knowledge"
            fallback_reason = sections[0].fallback_reason if sections else "no_relevant_source"

        cards: list[SourceCard] = []
        seen: set[tuple[int, int]] = set()
        for section in sections:
            for key in section.source_keys:
                source = source_map[key]
                marker = (source.document_id, source.chunk_id)
                if marker in seen:
                    continue
                seen.add(marker)
                if source.page_start is None:
                    reference = "Dokumen sumber"
                elif source.page_end in {None, source.page_start}:
                    reference = f"Halaman {source.page_start}"
                else:
                    reference = f"Halaman {source.page_start}-{source.page_end}"
                cards.append(
                    SourceCard(
                        document_id=source.document_id,
                        chunk_id=source.chunk_id,
                        title=source.title,
                        page_start=source.page_start,
                        page_end=source.page_end,
                        section=source.section_title,
                        reference_label=reference,
                        relevance_score=source.score,
                    )
                )
        return tuple(sections), tuple(cards), public_status, fallback_reason
