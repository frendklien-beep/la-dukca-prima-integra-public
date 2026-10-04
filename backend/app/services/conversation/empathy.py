from __future__ import annotations

SIGNALS = (
    (
        "complaint",
        ("bolak-balik", "lama sekali", "ribet", "tidak ada kejelasan"),
        (
            "Saya memahami situasi tersebut membuat proses terasa tidak nyaman; "
            "mari kita periksa ketentuan yang tersedia."
        ),
    ),
    (
        "difficulty",
        ("sulit", "kesulitan", "tidak bisa", "gagal mengurus"),
        (
            "Saya memahami prosesnya terasa menyulitkan; berikut informasi "
            "yang dapat membantu Anda menyiapkannya."
        ),
    ),
    (
        "confusion",
        ("bingung", "tidak mengerti", "kurang paham", "mohon jelaskan"),
        (
            "Saya memahami informasinya bisa terasa membingungkan; mari kita "
            "susun langkahnya dengan jelas."
        ),
    ),
    (
        "urgency",
        ("segera", "mendesak", "dibutuhkan cepat"),
        (
            "Saya memahami dokumen tersebut sedang dibutuhkan; berikut langkah "
            "yang dapat dipersiapkan berdasarkan informasi resmi."
        ),
    ),
)


def detect_empathy(message: str) -> tuple[str, str | None]:
    lowered = message.casefold()
    for mode, terms, phrase in SIGNALS:
        if any(term in lowered for term in terms):
            return mode, phrase
    return "none", None
