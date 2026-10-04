from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import (
    AiServiceUnavailableAppError,
    ChatRateLimitedError,
    ChatSessionBusyError,
    KnowledgeUnavailableAppError,
)
from app.domain.conversation import (
    ChatServiceResult,
    ConversationPlan,
    IntentRetrievalResult,
    PlannedIntent,
)
from app.models.public_chat_session import PublicChatSession
from app.repositories.chat_repository import ChatRepository
from app.services.conversation.clarification import ClarificationPlanner
from app.services.conversation.diagnostics import DiagnosticTrace
from app.services.conversation.empathy import detect_empathy
from app.services.conversation.formatter import MarkdownFormatter
from app.services.conversation.greeting import greeting_for
from app.services.conversation.human_context import HumanContextAnalyzer
from app.services.conversation.intents import detect_intents_detailed
from app.services.conversation.openai_chat import (
    GenerationError,
    GenerationProvider,
    GenerationTimeoutError,
    InvalidGenerationError,
)
from app.services.conversation.orchestrator import ResponseOrchestrator
from app.services.conversation.planner import KnowledgePlanner
from app.services.conversation.privacy import inspect_message
from app.services.conversation.retrieval import KnowledgeUnavailableError, RetrievalEngine
from app.services.conversation.runtime import PublicChatRateLimiter, SessionLockRegistry
from app.services.conversation.service_dependencies import ServiceDependencyPlanner
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

PRIVACY_NOTICE = (
    "Jangan kirimkan NIK lengkap, nomor KK, password, PIN, kode OTP, atau dokumen "
    "pribadi melalui chat."
)
SENSITIVE_ANSWER = (
    "Demi keamanan, jangan kirimkan NIK lengkap, nomor KK, OTP, PIN, password, "
    "token, atau isi dokumen pribadi. Silakan ajukan pertanyaan layanan tanpa "
    "menyertakan data tersebut."
)
OUT_OF_SCOPE_ANSWER = (
    "Saya membantu informasi layanan administrasi kependudukan dan pencatatan sipil "
    "berdasarkan Knowledge Base resmi. Silakan ajukan pertanyaan terkait layanan Dukcapil."
)
CLARIFICATION_ANSWER = (
    "Mohon sebutkan layanan Dukcapil yang dimaksud, misalnya KTP Elektronik, Kartu "
    "Keluarga, Akta Kelahiran, Akta Kematian, KIA, atau layanan pindah domisili."
)


class ChatService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        retrieval: RetrievalEngine,
        generator: GenerationProvider,
        repository: ChatRepository | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.retrieval = retrieval
        self.generator = generator
        self.repository = repository or ChatRepository()
        self.context_analyzer = HumanContextAnalyzer()
        self.clarification_planner = ClarificationPlanner()
        self.service_dependency_planner = ServiceDependencyPlanner()
        self.planner = KnowledgePlanner()
        self.orchestrator = ResponseOrchestrator()
        self.formatter = MarkdownFormatter()
        self.locks = SessionLockRegistry()
        self.rate_limiter = PublicChatRateLimiter(
            settings.public_chat_rate_limit_per_minute,
            settings.public_chat_rate_limit_burst,
        )

    def _resolve(self, session_id: UUID | None, now):
        with self.session_factory() as db:
            with db.begin():
                entity, is_new = self.repository.resolve_session(
                    db,
                    requested_id=session_id,
                    now=now,
                    session_hours=self.settings.public_chat_session_hours,
                )
                result = (
                    UUID(entity.id),
                    is_new,
                    entity.greeting_sent_at is not None,
                )
            return result

    def _load_context(self, session_id: UUID):
        with self.session_factory() as db:
            return self.repository.recent_messages(
                db,
                str(session_id),
                self.settings.public_chat_context_messages,
            )

    def _persist(
        self,
        *,
        session_id: UUID,
        safe_message: str,
        answer: str,
        status: str,
        error_code: str | None,
        sources,
        now,
        claim_greeting: bool,
    ) -> int:
        with self.session_factory() as db:
            with db.begin():
                entity = db.get(PublicChatSession, str(session_id))
                if entity is None:
                    raise RuntimeError("Sesi chat tidak ditemukan.")
                message = self.repository.persist_turn(
                    db,
                    chat_session=entity,
                    safe_user_content=safe_message,
                    assistant_content=answer,
                    response_status=status,
                    error_code=error_code,
                    sources=sources,
                    now=now,
                    claim_greeting=claim_greeting,
                    session_hours=self.settings.public_chat_session_hours,
                )
                message_id = message.id
            return int(message_id)

    def _settings_snapshot(self):
        with self.session_factory() as db:
            return settings_service.get_snapshot(db, self.settings)

    @staticmethod
    def _mark_ai_disabled(plans: tuple[PlannedIntent, ...]) -> tuple[PlannedIntent, ...]:
        return tuple(
            replace(
                plan,
                retrieval=IntentRetrievalResult(
                    intent_id=plan.intent_id,
                    status="ai_disabled",
                    top_score=None,
                    source_contexts=(),
                    fallback_reason="ai_disabled",
                    has_unresolved_conflict=False,
                    context_token_count=0,
                ),
            )
            for plan in plans
        )

    @staticmethod
    def _prioritize_intents(intents, priority_hints: tuple[str, ...]):
        if not priority_hints:
            return intents
        priority = {intent_id: index for index, intent_id in enumerate(priority_hints)}
        return tuple(
            sorted(
                intents,
                key=lambda item: (
                    priority.get(item.intent_id, len(priority)),
                    item.original_order,
                ),
            )
        )

    def _diagnose_retrieval(
        self, trace: DiagnosticTrace, planned: tuple[PlannedIntent, ...]
    ) -> None:
        sources = [
            source
            for item in planned
            if item.retrieval
            for source in item.retrieval.source_contexts
        ]
        trace.retrieval = {
            "queries": [item.query.canonical_label for item in planned],
            "documents_found": len({source.document_id for source in sources}),
            "top_sources": [
                {
                    "document_id": source.document_id,
                    "title": source.title,
                    "source_key": source.source_key,
                }
                for source in sources[:5]
            ],
            "top_score": max((source.score for source in sources), default=0.0),
            "fallback_reason": next(
                (
                    item.retrieval.fallback_reason
                    for item in planned
                    if item.retrieval and item.retrieval.fallback_reason
                ),
                None,
            ),
        }
        trace.regulatory_resolution = {
            "active_sources": [source.source_key for source in sources],
            "excluded_sources": sorted(
                {
                    document_id
                    for item in planned
                    if item.retrieval
                    for document_id in item.retrieval.excluded_source_ids
                }
            ),
            "conflicts": list(
                dict.fromkeys(
                    conflict
                    for item in planned
                    if item.retrieval
                    for conflict in item.retrieval.regulatory_conflicts
                )
            ),
        }

    async def send_message(
        self,
        *,
        message: str,
        session_id: UUID | None,
        request_id: str,
        client_key: str,
        now_utc,
    ) -> ChatServiceResult:
        trace = DiagnosticTrace(request_id, self.settings.ai_diagnostic_logging)
        retry_after = self.rate_limiter.check(client_key)
        if retry_after is not None:
            trace.emit("error")
            raise ChatRateLimitedError(retry_after)

        resolved_id, _is_new, greeting_sent = self._resolve(session_id, now_utc)
        lock_key = str(resolved_id)
        lock = self.locks.get(lock_key)
        if lock.locked():
            trace.emit("error")
            raise ChatSessionBusyError()

        try:
            async with lock:
                trace.stage_start("privacy_gate")
                privacy = inspect_message(message)
                trace.stage_end("privacy_gate")
                trace.privacy = {
                    "redaction_applied": privacy.blocked,
                    "risk": "high" if privacy.blocked else "low",
                    "reason": privacy.reason,
                    "prompt_injection_signal": privacy.prompt_injection_signal,
                }
                if privacy.blocked:
                    answer = SENSITIVE_ANSWER
                    message_id = self._persist(
                        session_id=resolved_id,
                        safe_message=privacy.safe_message,
                        answer=answer,
                        status="blocked_sensitive_data",
                        error_code=None,
                        sources=(),
                        now=now_utc,
                        claim_greeting=False,
                    )
                    trace.emit("fallback")
                    return ChatServiceResult(
                        session_id=resolved_id,
                        message_id=message_id,
                        status="blocked_sensitive_data",
                        answer=answer,
                        sources=(),
                        fallback_reason="sensitive_data",
                        privacy_notice=PRIVACY_NOTICE,
                    )

                recent = self._load_context(resolved_id)
                trace.stage_start("human_context")
                human_context = self.context_analyzer.analyze(privacy.safe_message)
                trace.stage_end("human_context")
                trace.human_context = human_context.diagnostic_summary()
                trace.privacy["risk"] = human_context.privacy_risk

                trace.stage_start("intent_detection")
                detection = detect_intents_detailed(
                    privacy.safe_message,
                    recent_messages=recent,
                    max_intents=self.settings.conversation_max_intents,
                )
                trace.stage_end("intent_detection")
                trace.intents = [item.diagnostic_summary() for item in detection.intents]
                if detection.low_confidence_candidates:
                    trace.intents.extend(
                        {
                            **item.diagnostic_summary(),
                            "below_threshold": True,
                        }
                        for item in detection.low_confidence_candidates
                    )

                trace.stage_start("clarification_planning")
                clarification = self.clarification_planner.build(
                    message=privacy.safe_message,
                    detection=detection,
                    human_context=human_context,
                )
                trace.stage_end("clarification_planning")
                trace.clarification = clarification.diagnostic_summary()

                ambiguous = bool(
                    not detection.intents and re_search_ambiguous(privacy.safe_message)
                )
                if not detection.intents:
                    status = (
                        "insufficient_knowledge"
                        if ambiguous or detection.is_domain or clarification.needs_clarification
                        else "out_of_scope"
                    )
                    if clarification.questions:
                        questions = "\n".join(
                            f"{index}. {question}"
                            for index, question in enumerate(clarification.questions, start=1)
                        )
                        body = f"Agar jawabannya tepat, mohon konfirmasi:\n{questions}"
                    else:
                        body = (
                            CLARIFICATION_ANSWER
                            if status == "insufficient_knowledge"
                            else OUT_OF_SCOPE_ANSWER
                        )
                    message_id = self._persist(
                        session_id=resolved_id,
                        safe_message=privacy.safe_message,
                        answer=body,
                        status=status,
                        error_code=None,
                        sources=(),
                        now=now_utc,
                        claim_greeting=False,
                    )
                    trace.emit("fallback")
                    return ChatServiceResult(
                        session_id=resolved_id,
                        message_id=message_id,
                        status=status,
                        answer=body,
                        sources=(),
                        fallback_reason=(
                            "clarification_required"
                            if status == "insufficient_knowledge"
                            else "out_of_scope"
                        ),
                        privacy_notice=PRIVACY_NOTICE,
                    )

                intents = self._prioritize_intents(detection.intents, human_context.priority_hints)
                initial_service_plan = self.service_dependency_planner.build_initial(
                    intents=intents,
                    human_context=human_context,
                )
                trace.service_plan = initial_service_plan.diagnostic_summary()

                greeting_text = None if greeting_sent else greeting_for(now_utc)
                generic_mode, generic_empathy = detect_empathy(privacy.safe_message)
                empathy_text = human_context.empathy_text or generic_empathy
                empathy_mode = (
                    human_context.empathy_mode if human_context.empathy_text else generic_mode
                )
                plan = ConversationPlan(
                    intents=intents,
                    human_context=human_context,
                    greeting_text=greeting_text,
                    empathy_text=empathy_text,
                    empathy_mode=empathy_mode,
                    is_out_of_scope=not detection.is_domain,
                    needs_clarification=clarification.needs_clarification,
                    overflow_count=detection.overflow_count,
                    prompt_injection_signal=privacy.prompt_injection_signal,
                    clarification=clarification,
                    service_plan=initial_service_plan,
                )
                planned = self.planner.build(plan.intents)
                snapshot = self._settings_snapshot()
                trace.stage_start("retrieval")
                if not snapshot.editable.knowledge_base_enabled:
                    planned = await self.retrieval.retrieve(
                        planned,
                        knowledge_base_enabled=False,
                    )
                elif not snapshot.editable.ai_enabled:
                    planned = self._mark_ai_disabled(planned)
                else:
                    try:
                        planned = await self.retrieval.retrieve(
                            planned,
                            knowledge_base_enabled=True,
                        )
                    except KnowledgeUnavailableError as exc:
                        raise KnowledgeUnavailableAppError() from exc
                trace.stage_end("retrieval")
                self._diagnose_retrieval(trace, planned)

                service_plan = self.service_dependency_planner.finalize(
                    initial=initial_service_plan,
                    plans=planned,
                )
                if any(
                    item.retrieval and item.retrieval.has_unresolved_conflict for item in planned
                ):
                    service_plan = replace(
                        service_plan,
                        requires_human_verification=True,
                    )
                trace.service_plan = service_plan.diagnostic_summary()

                supported = tuple(
                    item
                    for item in planned
                    if item.retrieval and item.retrieval.status == "supported"
                )
                generated = None
                if supported and snapshot.editable.ai_enabled:
                    trace.stage_start("openai_generation")
                    try:
                        generated = await self.generator.generate(
                            plans=planned,
                            recent_messages=recent[-self.settings.openai_history_max_messages :],
                            current_message=privacy.safe_message,
                            human_context=human_context,
                            request_id=request_id,
                        )
                    except GenerationTimeoutError as exc:
                        raise AiServiceUnavailableAppError("OPENAI_TIMEOUT") from exc
                    except InvalidGenerationError as exc:
                        raise AiServiceUnavailableAppError("AI_RESPONSE_INVALID") from exc
                    except GenerationError as exc:
                        raise AiServiceUnavailableAppError() from exc
                    finally:
                        trace.stage_end("openai_generation")
                    pop_diagnostics = getattr(self.generator, "pop_diagnostics", None)
                    if callable(pop_diagnostics):
                        trace.set_generation(pop_diagnostics(request_id))

                trace.stage_start("response_validation")
                sections, cards, public_status, fallback_reason = self.orchestrator.build(
                    plans=planned,
                    generated=generated,
                )
                logger.info(
                    "orchestrator_input request_id=%s generated_status=%s "
                    "generated_answers=%s planned_retrievals=%s",
                    request_id,
                    generated.status if generated else None,
                    [
                        {
                            "intent_id": answer.intent_id,
                            "status": answer.status,
                            "used_source_keys": answer.used_source_keys,
                        }
                        for answer in (generated.intent_answers if generated else [])
                    ],
                    [
                        {
                            "intent_id": item.intent_id,
                            "retrieval_status": item.retrieval.status if item.retrieval else None,
                            "source_keys": [
                                source.source_key
                                for source in (
                                    item.retrieval.source_contexts if item.retrieval else ()
                                )
                            ],
                        }
                        for item in planned
                    ],
                )
                trace.stage_end("response_validation")
                grounding_results = [
                    section.grounding.diagnostic_summary()
                    for section in sections
                    if section.grounding is not None
                ]
                trace.validation = {
                    "sections": grounding_results,
                    "unsupported_claims_detected": any(
                        result["unsupported_claims_detected"] for result in grounding_results
                    ),
                    "grounding_status": (
                        "passed"
                        if grounding_results
                        and all(
                            result["grounding_status"] == "passed" for result in grounding_results
                        )
                        else "warning"
                        if grounding_results
                        else "not_applicable"
                    ),
                }

                privacy_reminder = (
                    "Catatan privasi: jangan menuliskan NIK lengkap, nomor KK, atau data "
                    "identitas pribadi pada chat."
                    if human_context.privacy_risk in {"medium", "high"}
                    else None
                )
                answer = self.formatter.format(
                    sections=sections,
                    greeting_text=plan.greeting_text,
                    empathy_text=plan.empathy_text,
                    overflow_count=plan.overflow_count,
                    human_context=human_context,
                    service_plan=service_plan,
                    clarification=clarification,
                    privacy_reminder=privacy_reminder,
                )
                message_id = self._persist(
                    session_id=resolved_id,
                    safe_message=privacy.safe_message,
                    answer=answer,
                    status=public_status,
                    error_code=None,
                    sources=cards,
                    now=now_utc,
                    claim_greeting=bool(plan.greeting_text),
                )
                logger.info(
                    "chat_completed request_id=%s intent_count=%s supported_intent_count=%s "
                    "source_count=%s status=%s",
                    request_id,
                    len(planned),
                    len(supported),
                    len(cards),
                    public_status,
                )
                trace.emit("success" if public_status == "success" else "fallback")
                return ChatServiceResult(
                    session_id=resolved_id,
                    message_id=message_id,
                    status=public_status,
                    answer=answer,
                    sources=cards,
                    fallback_reason=fallback_reason,
                    privacy_notice=PRIVACY_NOTICE,
                )
        except Exception:
            trace.emit("error")
            raise
        finally:
            self.locks.discard_if_idle(lock_key)

    def close_session(self, *, session_id: UUID, now_utc) -> None:
        with self.session_factory() as db:
            with db.begin():
                self.repository.close_session(db, session_id, now_utc)


def re_search_ambiguous(message: str) -> bool:
    lowered = message.casefold().strip()
    return lowered in {
        "bagaimana cara mengurusnya?",
        "bagaimana cara mengurusnya",
        "syaratnya apa?",
        "syaratnya apa",
        "berapa lama?",
        "berapa lama",
        "kalau hilang?",
        "kalau hilang",
    }
