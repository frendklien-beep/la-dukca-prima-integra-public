import json
from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from app.domain.conversation import DetectedIntent
from app.repositories.retrieval_repository import (
    RetrievalChunkRecord,
    RetrievalDocumentRecord,
)
from app.services.conversation.planner import KnowledgePlanner
from app.services.conversation.retrieval import (
    KnowledgeUnavailableError,
    RetrievalEngine,
)
from app.services.knowledge.types import EmbeddingBatch


class FakeRepository:
    def __init__(self, documents):
        self.documents = tuple(documents)

    def eligible_documents(self, _session):
        return self.documents


class FakeEmbeddingProvider:
    def __init__(self, vectors):
        self.vectors = tuple(tuple(v) for v in vectors)
        self.calls = []

    async def embed(self, texts):
        self.calls.append(tuple(texts))
        return EmbeddingBatch(self.vectors, "fake", len(self.vectors[0]), (), None)


def _plan(intent_id="ktp_el", label="KTP Elektronik", order=1, segment="syarat KTP"):
    intent = DetectedIntent(intent_id, label, order, segment, 1.0, "alias")
    return KnowledgePlanner().build((intent,))[0]


def _document(document_id=1, index_version="v1", chunks=None):
    chunks = chunks or (
        RetrievalChunkRecord(
            11, document_id, "Syarat KTP Elektronik resmi", "a", 1, 1, "Persyaratan", 10
        ),
        RetrievalChunkRecord(12, document_id, "Langkah KTP Elektronik", "b", 2, 2, "Prosedur", 10),
        RetrievalChunkRecord(13, document_id, "Informasi tambahan KTP", "c", 3, 3, "Informasi", 10),
    )
    return RetrievalDocumentRecord(
        document_id,
        "SOP KTP Elektronik",
        "sop",
        6,
        "city",
        date(2026, 1, 1),
        index_version,
        None,
        "active",
        tuple(chunks),
    )


def _write_index(settings, document, vectors):
    path = settings.indexes_dir / "documents" / str(document.id) / document.index_version
    path.mkdir(parents=True, exist_ok=True)
    matrix = np.asarray(vectors, dtype=np.float32)
    matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    np.save(path / "embeddings.npy", matrix, allow_pickle=False)
    metadata = [{"chunk_id": chunk.id} for chunk in document.chunks]
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


@pytest.mark.asyncio
async def test_no_active_documents_skips_embedding(app, test_settings) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0]])
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=provider,
        repository=FakeRepository(()),
    )
    result = await engine.retrieve((_plan(),), knowledge_base_enabled=True)
    assert result[0].retrieval.status == "no_active_documents"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_retrieval_assigns_intent_namespace_and_two_chunk_limit(app, test_settings) -> None:
    document = _document()
    _write_index(test_settings, document, [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]])
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
        repository=FakeRepository((document,)),
    )
    result = await engine.retrieve((_plan(),), knowledge_base_enabled=True)
    retrieval = result[0].retrieval
    assert retrieval.status == "supported"
    assert len(retrieval.source_contexts) == 2
    assert [source.source_key for source in retrieval.source_contexts] == ["I1-S1", "I1-S2"]


@pytest.mark.asyncio
async def test_below_threshold_has_honest_fallback(app, test_settings) -> None:
    document = _document(
        chunks=(RetrievalChunkRecord(11, 1, "Materi tidak terkait", "a", 1, 1, None, 5),)
    )
    _write_index(test_settings, document, [[0.0, 1.0]])
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
        repository=FakeRepository((document,)),
    )
    result = await engine.retrieve((_plan(),), knowledge_base_enabled=True)
    assert result[0].retrieval.status == "below_threshold"
    assert result[0].retrieval.fallback_reason == "insufficient_retrieval_confidence"


@pytest.mark.asyncio
async def test_corrupt_index_is_technical_failure(app, test_settings) -> None:
    document = _document()
    path = test_settings.indexes_dir / "documents" / "1" / "v1"
    path.mkdir(parents=True)
    (path / "embeddings.npy").write_bytes(b"bad")
    (path / "metadata.json").write_text("[]", encoding="utf-8")
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
        repository=FakeRepository((document,)),
    )
    with pytest.raises(KnowledgeUnavailableError):
        await engine.retrieve((_plan(),), knowledge_base_enabled=True)


@pytest.mark.asyncio
async def test_multi_intent_source_namespaces_are_isolated(app, test_settings) -> None:
    document = _document()
    _write_index(test_settings, document, [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]])
    provider = FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0]])
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=provider,
        repository=FakeRepository((document,)),
    )
    plans = (
        _plan("ktp_el", "KTP Elektronik", 1, "KTP"),
        replace(_plan("kartu_keluarga", "Kartu Keluarga", 2, "KK"), sequence=2),
    )
    result = await engine.retrieve(plans, knowledge_base_enabled=True)
    assert all(
        source.source_key.startswith("I1-") for source in result[0].retrieval.source_contexts
    )
    assert all(
        source.source_key.startswith("I2-") for source in result[1].retrieval.source_contexts
    )


@pytest.mark.asyncio
async def test_knowledge_base_disabled_skips_embedding(app, test_settings) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0]])
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=provider,
        repository=FakeRepository((_document(),)),
    )
    result = await engine.retrieve((_plan(),), knowledge_base_enabled=False)
    assert result[0].retrieval.status == "knowledge_base_disabled"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_equal_authority_contradiction_becomes_conflict(app, test_settings) -> None:
    chunks = (
        RetrievalChunkRecord(11, 1, "Fotokopi dokumen wajib dilampirkan", "a", 1, 1, "Syarat", 10),
        RetrievalChunkRecord(
            12, 1, "Fotokopi dokumen tidak wajib dilampirkan", "b", 2, 2, "Syarat", 10
        ),
    )
    document = _document(chunks=chunks)
    _write_index(test_settings, document, [[1.0, 0.0], [1.0, 0.0]])
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
        repository=FakeRepository((document,)),
    )
    result = await engine.retrieve((_plan(),), knowledge_base_enabled=True)
    assert result[0].retrieval.status == "conflict"
    assert result[0].retrieval.fallback_reason == "source_conflict"
    # Remediation v1.1 preserves conflicting sources so the public fallback can cite them.
    assert len(result[0].retrieval.source_contexts) == 2
    assert {item.source_key for item in result[0].retrieval.source_contexts} == {"I1-S1", "I1-S2"}


@pytest.mark.asyncio
async def test_unverified_regulation_does_not_block_safe_service_source(
    app,
    test_settings,
) -> None:
    sop = _document(
        document_id=1,
        chunks=(
            RetrievalChunkRecord(
                11,
                1,
                "KTP-el yang rusak atau hangus dapat diajukan untuk penggantian.",
                "sop-ktp",
                1,
                1,
                "Penggantian KTP-el",
                14,
            ),
        ),
    )
    regulation = replace(
        _document(
            document_id=2,
            chunks=(
                RetrievalChunkRecord(
                    21,
                    2,
                    "Ketentuan mengenai penggantian KTP-el yang rusak atau hangus.",
                    "perpres-ktp",
                    1,
                    1,
                    "Ketentuan KTP-el",
                    14,
                ),
            ),
        ),
        title="PERPRES NO 96 TAHUN 2018",
        category="peraturan",
        authority_rank=4,
        jurisdiction="national",
        document_number="96",
        document_year=2018,
        document_type="regulation",
        legal_status="unknown",
    )

    _write_index(test_settings, sop, [[1.0, 0.0]])
    _write_index(test_settings, regulation, [[1.0, 0.0]])

    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
        repository=FakeRepository((sop, regulation)),
    )

    result = await engine.retrieve(
        (
            _plan(
                segment="dokumen terbakar KTP hangus bagaimana mengurusnya",
            ),
        ),
        knowledge_base_enabled=True,
    )
    retrieval = result[0].retrieval

    assert retrieval.status == "supported"
    assert retrieval.fallback_reason is None
    assert retrieval.has_unresolved_conflict is False
    assert retrieval.source_contexts
    assert {source.document_id for source in retrieval.source_contexts} == {1}


@pytest.mark.asyncio
async def test_only_unverified_regulation_remains_conflict(
    app,
    test_settings,
) -> None:
    regulation = replace(
        _document(
            document_id=2,
            chunks=(
                RetrievalChunkRecord(
                    21,
                    2,
                    "Ketentuan mengenai penggantian KTP-el yang rusak atau hangus.",
                    "perpres-ktp",
                    1,
                    1,
                    "Ketentuan KTP-el",
                    14,
                ),
            ),
        ),
        title="PERPRES NO 96 TAHUN 2018",
        category="peraturan",
        authority_rank=4,
        jurisdiction="national",
        document_number="96",
        document_year=2018,
        document_type="regulation",
        legal_status="unknown",
    )

    _write_index(test_settings, regulation, [[1.0, 0.0]])

    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
        repository=FakeRepository((regulation,)),
    )

    result = await engine.retrieve(
        (
            _plan(
                segment="dokumen terbakar KTP hangus bagaimana mengurusnya",
            ),
        ),
        knowledge_base_enabled=True,
    )
    retrieval = result[0].retrieval

    assert retrieval.status == "conflict"
    assert retrieval.fallback_reason == "regulatory_verification_required"
    assert retrieval.has_unresolved_conflict is True
    assert {source.document_id for source in retrieval.source_contexts} == {2}


@pytest.mark.asyncio
async def test_global_budget_keeps_one_source_per_supported_intent(app, test_settings) -> None:
    content_a = "KTP Elektronik " + ("persyaratan " * 60)
    content_b = "Kartu Keluarga " + ("dokumen " * 60)
    chunks = (
        RetrievalChunkRecord(11, 1, content_a, "a", 1, 1, "KTP", 150),
        RetrievalChunkRecord(12, 1, content_b, "b", 2, 2, "KK", 150),
        RetrievalChunkRecord(13, 1, "Tambahan " * 80, "c", 3, 3, "Tambahan", 160),
    )
    document = _document(chunks=chunks)
    _write_index(test_settings, document, [[1.0, 0.0], [1.0, 0.0], [0.9, 0.1]])
    test_settings.retrieval_context_max_tokens = 300
    test_settings.retrieval_context_per_intent_tokens = 1000
    engine = RetrievalEngine(
        settings=test_settings,
        session_factory=app.state.session_factory,
        embedding_provider=FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0]]),
        repository=FakeRepository((document,)),
    )
    plans = (
        _plan("ktp_el", "KTP Elektronik", 1, "KTP"),
        replace(_plan("kartu_keluarga", "Kartu Keluarga", 2, "KK"), sequence=2),
    )
    result = await engine.retrieve(plans, knowledge_base_enabled=True)
    assert all(plan.retrieval.source_contexts for plan in result)
    assert sum(len(plan.retrieval.source_contexts) for plan in result) <= 4
