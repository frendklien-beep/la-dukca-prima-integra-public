from app.domain.conversation import RecentMessage
from app.services.conversation.intents import detect_intents


def ids(message: str):
    return [item.intent_id for item in detect_intents(message)[0]]


def test_single_intent() -> None:
    assert ids("Apa syarat membuat KTP-el?") == ["ktp_el"]


def test_multi_intent_preserves_first_order() -> None:
    assert ids("Bagaimana KTP, Kartu Keluarga, dan Akta Kematian?") == [
        "ktp_el",
        "kartu_keluarga",
        "akta_kematian",
    ]


def test_duplicate_alias_merges() -> None:
    assert ids("KTP hilang dan bagaimana cetak ulang e-KTP?") == ["ktp_el"]


def test_followup_inherits_latest_safe_user_intent() -> None:
    recent = (
        RecentMessage(role="user", content="Bagaimana mengurus KIA?"),
        RecentMessage(role="assistant", content="Jawaban"),
    )
    intents, overflow, is_domain = detect_intents("Kalau hilang bagaimana?", recent_messages=recent)
    assert [item.intent_id for item in intents] == ["kia"]
    assert intents[0].detection_method == "bounded_follow_up"
    assert overflow == 0
    assert is_domain is True


def test_maximum_five_intents_discloses_overflow() -> None:
    intents, overflow, _ = detect_intents(
        "KTP, KK, Akta Kelahiran, Akta Kematian, KIA, IKD, dan surat pindah",
        max_intents=5,
    )
    assert len(intents) == 5
    assert overflow >= 1


def test_generic_domain_intent() -> None:
    intents, _, _ = detect_intents("Saya ingin bertanya layanan Dukcapil")
    assert intents[0].intent_id == "layanan_dukcapil_lainnya"


def test_unrelated_question_has_no_intent() -> None:
    assert detect_intents("Bagaimana cuaca besok?")[0] == ()
