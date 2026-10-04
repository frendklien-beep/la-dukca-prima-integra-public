from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.domain.conversation import (
    IntentRetrievalResult,
    PlannedIntent,
    SourceContext,
)
from app.repositories.retrieval_repository import (
    RetrievalDocumentRecord,
    RetrievalRepository,
)
from app.services.conversation.regulatory import RegulatoryResolver
from app.services.knowledge.types import EmbeddingBatch


class KnowledgeUnavailableError(RuntimeError):
    pass


class QueryEmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch: ...


_TOKEN = re.compile(r"[a-z0-9]+", re.I)


def _terms(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(value) if len(token) > 1}


def _lexical_score(query: str, text: str, service_terms: tuple[str, ...]) -> tuple[float, bool]:
    lowered = text.casefold()
    exact = any(term.casefold() in lowered for term in service_terms)
    query_terms = _terms(query)
    text_terms = _terms(text)
    overlap = len(query_terms & text_terms) / max(1, len(query_terms))
    return min(1.0, overlap + (0.35 if exact else 0.0)), exact


def _estimated_tokens(content: str) -> int:
    return max(1, len(content) // 4)


def _near_duplicate(left: str, right: str) -> bool:
    left_terms = _terms(left)
    right_terms = _terms(right)
    if not left_terms or not right_terms:
        return left.strip().casefold() == right.strip().casefold()
    return len(left_terms & right_terms) / len(left_terms | right_terms) >= 0.90


def _has_unresolved_conflict(sources: Sequence[SourceContext]) -> bool:
    contradiction_pairs = (
        ("wajib", "tidak wajib"),
        ("diperlukan", "tidak diperlukan"),
        ("harus", "tidak harus"),
    )
    for index, left in enumerate(sources):
        for right in sources[index + 1 :]:
            if left.authority_rank != right.authority_rank:
                continue
            left_text = left.content.casefold()
            right_text = right.content.casefold()
            for positive, negative in contradiction_pairs:
                if (positive in left_text and negative in right_text) or (
                    negative in left_text and positive in right_text
                ):
                    return True
    return False


def _apply_global_budget(
    plans: tuple[PlannedIntent, ...],
    *,
    maximum_tokens: int,
) -> tuple[PlannedIntent, ...]:
    supported = [plan for plan in plans if plan.retrieval and plan.retrieval.status == "supported"]
    total = sum(plan.retrieval.context_token_count for plan in supported if plan.retrieval)
    if total <= maximum_tokens:
        return plans

    selected_by_intent: dict[str, list[SourceContext]] = {plan.intent_id: [] for plan in supported}
    used_tokens = 0
    # Fairness invariant: keep one source for every supported intent first.
    for plan in supported:
        source = plan.retrieval.source_contexts[0]
        selected_by_intent[plan.intent_id].append(source)
        used_tokens += _estimated_tokens(source.content)
    depth = 1
    while used_tokens < maximum_tokens:
        added = False
        for plan in supported:
            contexts = plan.retrieval.source_contexts
            if depth >= len(contexts):
                continue
            source = contexts[depth]
            cost = _estimated_tokens(source.content)
            if used_tokens + cost > maximum_tokens:
                continue
            selected_by_intent[plan.intent_id].append(source)
            used_tokens += cost
            added = True
        if not added:
            break
        depth += 1

    output: list[PlannedIntent] = []
    for plan in plans:
        retrieval = plan.retrieval
        if retrieval and retrieval.status == "supported":
            selected = tuple(
                replace(source, source_key=f"I{plan.sequence}-S{index}")
                for index, source in enumerate(selected_by_intent[plan.intent_id], start=1)
            )
            retrieval = replace(
                retrieval,
                source_contexts=selected,
                top_score=selected[0].score,
                context_token_count=sum(_estimated_tokens(item.content) for item in selected),
            )
            plan = replace(plan, retrieval=retrieval)
        output.append(plan)
    return tuple(output)


class RetrievalEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        embedding_provider: QueryEmbeddingProvider,
        repository: RetrievalRepository | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.embedding_provider = embedding_provider
        self.repository = repository or RetrievalRepository()
        self.regulatory_resolver = RegulatoryResolver()

    def _snapshot(self) -> tuple[RetrievalDocumentRecord, ...]:
        with self.session_factory() as session:
            return self.repository.eligible_documents(session)

    def _load_document_index(
        self, document: RetrievalDocumentRecord
    ) -> tuple[np.ndarray, list[dict[str, object]]]:
        version_dir = (
            self.settings.indexes_dir / "documents" / str(document.id) / document.index_version
        )
        vector_path = version_dir / "embeddings.npy"
        metadata_path = version_dir / "metadata.json"
        try:
            matrix = np.load(vector_path, allow_pickle=False)
            metadata = json.loads(metadata_path.read_text("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise KnowledgeUnavailableError("Index Knowledge Base tidak tersedia.") from exc
        if matrix.ndim != 2 or matrix.dtype != np.float32 or not np.all(np.isfinite(matrix)):
            raise KnowledgeUnavailableError("Index Knowledge Base tidak valid.")
        if not isinstance(metadata, list) or len(metadata) != matrix.shape[0]:
            raise KnowledgeUnavailableError("Metadata index tidak konsisten.")
        return matrix, metadata

    async def retrieve(
        self,
        plans: tuple[PlannedIntent, ...],
        *,
        knowledge_base_enabled: bool,
    ) -> tuple[PlannedIntent, ...]:
        if not knowledge_base_enabled:
            return tuple(
                replace(
                    plan,
                    retrieval=IntentRetrievalResult(
                        intent_id=plan.intent_id,
                        status="knowledge_base_disabled",
                        top_score=None,
                        source_contexts=(),
                        fallback_reason="knowledge_base_disabled",
                        has_unresolved_conflict=False,
                        context_token_count=0,
                    ),
                )
                for plan in plans
            )
        documents = self._snapshot()
        if not documents:
            return tuple(
                replace(
                    plan,
                    retrieval=IntentRetrievalResult(
                        intent_id=plan.intent_id,
                        status="no_active_documents",
                        top_score=None,
                        source_contexts=(),
                        fallback_reason="no_active_documents",
                        has_unresolved_conflict=False,
                        context_token_count=0,
                    ),
                )
                for plan in plans
            )

        embedding_batch = await self.embedding_provider.embed(
            [plan.query.normalized_query for plan in plans]
        )
        query_matrix = np.asarray(embedding_batch.vectors, dtype=np.float32)
        if query_matrix.ndim != 2 or query_matrix.shape[0] != len(plans):
            raise KnowledgeUnavailableError("Embedding query tidak valid.")
        norms = np.linalg.norm(query_matrix, axis=1, keepdims=True)
        if np.any(norms == 0) or not np.all(np.isfinite(norms)):
            raise KnowledgeUnavailableError("Embedding query tidak valid.")
        query_matrix = query_matrix / norms

        loaded: list[tuple[RetrievalDocumentRecord, np.ndarray, list[dict[str, object]]]] = []
        for document in documents:
            matrix, metadata = self._load_document_index(document)
            if matrix.shape[1] != query_matrix.shape[1]:
                raise KnowledgeUnavailableError("Dimensi index tidak sesuai.")
            loaded.append((document, matrix, metadata))

        output: list[PlannedIntent] = []
        for intent_index, plan in enumerate(plans):
            candidates: list[SourceContext] = []
            candidate_row_count = 0
            for document, matrix, metadata in loaded:
                semantic_scores = matrix @ query_matrix[intent_index]
                candidate_row_count += min(len(metadata), self.settings.retrieval_candidate_top_k)
                chunk_by_id = {chunk.id: chunk for chunk in document.chunks}
                for row_index in np.argsort(semantic_scores)[::-1][
                    : self.settings.retrieval_candidate_top_k
                ]:
                    row = metadata[int(row_index)]
                    chunk_id = int(row.get("chunk_id", -1))
                    chunk = chunk_by_id.get(chunk_id)
                    if chunk is None:
                        raise KnowledgeUnavailableError("Pemetaan chunk index tidak konsisten.")
                    semantic = float(semantic_scores[int(row_index)])
                    lexical, exact = _lexical_score(
                        plan.query.original_segment,
                        f"{document.title} {chunk.section_title or ''} {chunk.content}",
                        plan.query.service_terms,
                    )
                    title_section, _ = _lexical_score(
                        plan.query.original_segment,
                        f"{document.title} {chunk.section_title or ''}",
                        plan.query.service_terms,
                    )
                    score = 0.85 * semantic + 0.10 * lexical + 0.05 * title_section
                    passes = semantic >= self.settings.retrieval_min_cosine_score or (
                        exact and semantic >= self.settings.retrieval_exact_match_min_score
                    )
                    if not passes or not math.isfinite(score):
                        continue
                    candidates.append(
                        SourceContext(
                            source_key="",
                            intent_id=plan.intent_id,
                            document_id=document.id,
                            chunk_id=chunk.id,
                            title=document.title,
                            category=document.category,
                            authority_rank=document.authority_rank,
                            jurisdiction=document.jurisdiction,
                            effective_date=document.effective_date,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            section_title=chunk.section_title,
                            content=chunk.content,
                            score=score,
                            document_type=document.document_type,
                            document_number=document.document_number,
                            document_year=document.document_year,
                            legal_status=document.legal_status,
                            issuer=document.issuer,
                            amends=document.amends,
                            amended_by=document.amended_by,
                            revokes=document.revokes,
                            revoked_by=document.revoked_by,
                            topics=document.topics,
                        )
                    )

            candidates.sort(
                key=lambda item: (
                    -item.score,
                    item.authority_rank,
                    -(item.effective_date.toordinal() if item.effective_date else 0),
                    item.document_id,
                    item.chunk_id,
                )
            )
            selected: list[SourceContext] = []
            seen_content: set[str] = set()
            document_counts: defaultdict[int, int] = defaultdict(int)
            document_ids: set[int] = set()
            token_count = 0
            for candidate in candidates:
                content_key = re.sub(r"\s+", " ", candidate.content).strip().casefold()
                if content_key in seen_content or any(
                    _near_duplicate(candidate.content, existing.content) for existing in selected
                ):
                    continue
                if (
                    document_counts[candidate.document_id]
                    >= self.settings.retrieval_max_chunks_per_document
                ):
                    continue
                if (
                    candidate.document_id not in document_ids
                    and len(document_ids) >= self.settings.retrieval_max_documents
                ):
                    continue
                estimated_tokens = _estimated_tokens(candidate.content)
                if (
                    selected
                    and token_count + estimated_tokens
                    > self.settings.retrieval_context_per_intent_tokens
                ):
                    continue
                selected.append(candidate)
                seen_content.add(content_key)
                document_counts[candidate.document_id] += 1
                document_ids.add(candidate.document_id)
                token_count += estimated_tokens
                if len(selected) >= self.settings.retrieval_final_top_k:
                    break
            target_jurisdiction = (
                "tomohon"
                if "tomohon" in plan.query.original_segment.casefold()
                else "unknown"
                if any(
                    marker in plan.query.original_segment.casefold()
                    for marker in ("daerah lain", "luar daerah", "beda daerah")
                )
                else "tomohon"
            )
            resolution = self.regulatory_resolver.resolve(
                tuple(selected),
                target_jurisdiction=target_jurisdiction,
            )
            verification_warning_codes = {
                "regulatory_validity_unknown",
                "jurisdiction_mismatch",
            }
            safe_resolution_sources = tuple(
                source
                for source in resolution.sources
                if not verification_warning_codes.intersection(
                    source.regulatory_warnings
                )
            )
            use_safe_sources = bool(
                resolution.requires_human_verification
                and not resolution.conflicts
                and safe_resolution_sources
            )
            effective_sources = (
                safe_resolution_sources
                if use_safe_sources
                else resolution.sources
            )
            verification_required = bool(
                resolution.requires_human_verification
                and not use_safe_sources
            )

            resolved_selected = sorted(
                effective_sources,
                key=lambda item: (
                    -item.score,
                    item.authority_rank,
                    -(item.effective_date.toordinal() if item.effective_date else 0),
                    item.document_id,
                    item.chunk_id,
                ),
            )
            selected_with_keys = tuple(
                replace(candidate, source_key=f"I{plan.sequence}-S{index}")
                for index, candidate in enumerate(resolved_selected, start=1)
            )
            textual_conflict = _has_unresolved_conflict(selected_with_keys)
            conflict = bool(
                textual_conflict
                or resolution.conflicts
                or (verification_required and selected_with_keys)
            )
            if conflict:
                status = "conflict"
                fallback_reason = (
                    "regulatory_verification_required"
                    if verification_required
                    else "source_conflict"
                )

            elif selected_with_keys:
                status = "supported"
                fallback_reason = None
            elif candidate_row_count:
                status = "below_threshold"
                fallback_reason = "insufficient_retrieval_confidence"
            else:
                status = "no_candidates"
                fallback_reason = "no_relevant_source"
            token_count = sum(_estimated_tokens(item.content) for item in selected_with_keys)
            output.append(
                replace(
                    plan,
                    retrieval=IntentRetrievalResult(
                        intent_id=plan.intent_id,
                        status=status,
                        top_score=selected_with_keys[0].score if selected_with_keys else None,
                        source_contexts=selected_with_keys,
                        fallback_reason=fallback_reason,
                        has_unresolved_conflict=conflict,
                        context_token_count=token_count,
                        excluded_source_ids=resolution.excluded_document_ids,
                        regulatory_conflicts=resolution.conflicts,
                    ),
                )
            )
        return _apply_global_budget(
            tuple(output),
            maximum_tokens=self.settings.retrieval_context_max_tokens,
        )
