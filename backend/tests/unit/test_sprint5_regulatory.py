from dataclasses import replace
from datetime import date

from app.domain.conversation import SourceContext
from app.services.conversation.regulatory import (
    RegulatoryResolver,
    _jurisdiction_applicable,
    document_identifier,
    parse_relationships,
)


def make_source(
    *,
    document_id: int,
    source_key: str,
    title: str,
    status: str = "active",
    jurisdiction: str = "tomohon",
    document_number: str | None = None,
    document_year: int | None = None,
    effective_date: date | None = None,
    amends: tuple[str, ...] = (),
    revoked_by: tuple[str, ...] = (),
    score: float = 0.90,
) -> SourceContext:
    return SourceContext(
        source_key=source_key,
        intent_id="I1",
        document_id=document_id,
        chunk_id=document_id * 10,
        title=title,
        category="regulation",
        authority_rank=1,
        jurisdiction=jurisdiction,
        effective_date=effective_date,
        page_start=1,
        page_end=1,
        section_title="Ketentuan",
        content="Isi sumber resmi untuk pengujian.",
        score=score,
        document_type="regulation",
        document_number=document_number,
        document_year=document_year,
        legal_status=status,
        amends=amends,
        revoked_by=revoked_by,
    )


def test_parse_relationships_handles_empty_invalid_and_valid_values() -> None:
    assert parse_relationships(None) == ()
    assert parse_relationships("") == ()
    assert parse_relationships("bukan-json") == ()
    assert parse_relationships('{"value": 1}') == ()
    assert parse_relationships('["A", 12, "", null, {"x": 1}]') == ("A", "12")


def test_revoked_source_is_excluded() -> None:
    source = make_source(
        document_id=1,
        source_key="I1-S1",
        title="Peraturan Lama",
        status="revoked",
    )

    result = RegulatoryResolver().resolve((source,))

    assert result.sources == ()
    assert result.excluded_document_ids == (1,)


def test_active_revoker_excludes_revoked_document() -> None:
    old_source = make_source(
        document_id=1,
        source_key="I1-S1",
        title="Peraturan Lama",
        document_number="10",
        document_year=2020,
        revoked_by=("20/2024",),
    )
    revoker = make_source(
        document_id=2,
        source_key="I1-S2",
        title="Peraturan Pencabut",
        document_number="20",
        document_year=2024,
        status="active",
    )

    result = RegulatoryResolver().resolve((old_source, revoker))

    assert result.excluded_document_ids == (1,)
    assert [source.document_id for source in result.sources] == [2]


def test_superseded_source_is_deprioritized() -> None:
    source = make_source(
        document_id=3,
        source_key="I1-S1",
        title="Peraturan Tergantikan",
        status="superseded",
        score=0.90,
    )

    result = RegulatoryResolver().resolve((source,))
    resolved = result.sources[0]

    assert resolved.score == 0.75
    assert "superseded_source_deprioritized" in resolved.regulatory_warnings


def test_amended_source_receives_review_warning() -> None:
    source = make_source(
        document_id=4,
        source_key="I1-S1",
        title="Peraturan Diubah",
        status="amended",
        score=0.90,
    )

    result = RegulatoryResolver().resolve((source,))
    resolved = result.sources[0]

    assert resolved.score == 0.86
    assert "amended_source_reviewed_with_amendment" in resolved.regulatory_warnings


def test_unknown_regulatory_validity_requires_human_verification() -> None:
    source = make_source(
        document_id=5,
        source_key="I1-S1",
        title="Peraturan Tidak Diketahui",
        status="unknown",
        score=0.90,
    )

    result = RegulatoryResolver().resolve((source,))
    resolved = result.sources[0]

    assert resolved.score == 0.87
    assert "regulatory_validity_unknown" in resolved.regulatory_warnings
    assert result.requires_human_verification is True


def test_jurisdiction_mismatch_requires_human_verification() -> None:
    source = make_source(
        document_id=6,
        source_key="I1-S1",
        title="Peraturan Daerah Lain",
        jurisdiction="manado",
        score=0.90,
    )

    result = RegulatoryResolver().resolve(
        (source,),
        target_jurisdiction="tomohon",
    )
    resolved = result.sources[0]

    assert resolved.score == 0.65
    assert "jurisdiction_mismatch" in resolved.regulatory_warnings
    assert result.requires_human_verification is True


def test_newer_amendment_conflict_requires_verification() -> None:
    older_amendment = make_source(
        document_id=7,
        source_key="I1-S1",
        title="Peraturan Pengubah Lama",
        document_number="30",
        document_year=2022,
        effective_date=date(2022, 1, 1),
        amends=("40/2023",),
    )
    newer_target = make_source(
        document_id=8,
        source_key="I1-S2",
        title="Peraturan Lebih Baru",
        document_number="40",
        document_year=2023,
        effective_date=date(2023, 1, 1),
    )

    result = RegulatoryResolver().resolve((older_amendment, newer_target))

    assert result.conflicts
    assert result.conflicts[0].startswith("amendment_date_conflict:")
    assert result.requires_human_verification is True


def test_diagnostic_summary_is_safe_and_structured() -> None:
    source = make_source(
        document_id=9,
        source_key="I1-S1",
        title="Peraturan Aktif",
    )

    result = RegulatoryResolver().resolve((source,))
    summary = result.diagnostic_summary()

    assert summary["active_sources"] == ["I1-S1"]
    assert summary["excluded_sources"] == []
    assert summary["conflicts"] == []
    assert summary["requires_human_verification"] is False


def test_document_identifier_uses_number_without_year() -> None:
    source = make_source(
        document_id=10,
        source_key="I1-S1",
        title="Peraturan Bernomor",
        document_number="55",
    )

    assert document_identifier(source) == "55"


def test_missing_revoker_requires_verification_warning() -> None:
    source = make_source(
        document_id=11,
        source_key="I1-S1",
        title="Peraturan dengan Referensi Pencabut",
        status="active",
        revoked_by=("999/2099",),
    )

    result = RegulatoryResolver().resolve((source,))
    resolved = result.sources[0]

    assert resolved.document_id == 11
    assert "revocation_requires_verification" in resolved.regulatory_warnings


def test_explicit_revokes_relationship_excludes_target() -> None:
    target = make_source(
        document_id=12,
        source_key="I1-S1",
        title="Peraturan Lama",
        document_number="50",
        document_year=2020,
    )
    revoker = replace(
        make_source(
            document_id=13,
            source_key="I1-S2",
            title="Peraturan Baru",
            document_number="60",
            document_year=2024,
        ),
        revokes=("50/2020",),
    )

    result = RegulatoryResolver().resolve((target, revoker))

    assert result.excluded_document_ids == (12,)
    assert [source.document_id for source in result.sources] == [13]


def test_unknown_target_jurisdiction_accepts_local_source_only() -> None:
    assert _jurisdiction_applicable("tomohon", "unknown") is True
    assert _jurisdiction_applicable("local", "unknown") is True
    assert _jurisdiction_applicable("manado", "unknown") is False
