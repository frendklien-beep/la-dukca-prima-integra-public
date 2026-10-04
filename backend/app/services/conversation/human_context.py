from __future__ import annotations

import re
from collections.abc import Iterable

from app.domain.conversation import HumanContext
from app.services.conversation.urgency import UrgencyDetector

_RISK_ORDER = ("low", "medium", "high")
_EMPATHY_ORDER = ("none", "light", "supportive", "sensitive")


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


def _contains(pattern: re.Pattern[str], message: str) -> bool:
    return bool(pattern.search(message))


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _raise_level(current: str, candidate: str, order: tuple[str, ...]) -> str:
    return candidate if order.index(candidate) > order.index(current) else current


# Document loss is extracted separately so every explicit document can be preserved.
_DAMAGE_TERMS = (
    r"hilang|kehilangan|dicuri|dirampas|ditahan|rusak|hangus|terbakar|terendam|"
    r"hanyut|tertimbun|musnah|tidak ada|nyanda ada"
)
_DOCUMENT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("lost_ktp", "ktp_el", r"ktp(?:-?el| elektronik)?|e-?ktp|kartu tanda penduduk"),
    ("lost_family_card", "kartu_keluarga", r"kk|kartu keluarga"),
    (
        "lost_birth_certificate",
        "akta_kelahiran",
        r"akta kelahiran|akta lahir|surat kelahiran",
    ),
    (
        "lost_death_certificate",
        "akta_kematian",
        r"akta kematian|akta meninggal|surat kematian",
    ),
    ("lost_child_identity_card", "kia", r"kia|kartu identitas anak|kartu anak"),
    (
        "lost_marriage_certificate",
        "akta_perkawinan",
        r"akta perkawinan|akta nikah|buku nikah",
    ),
    (
        "lost_divorce_certificate",
        "akta_perceraian",
        r"akta perceraian|akta cerai",
    ),
)
_SERVICE_ORDER = (
    "ktp_el",
    "kartu_keluarga",
    "akta_kelahiran",
    "akta_kematian",
    "kia",
    "akta_perkawinan",
    "akta_perceraian",
    "perubahan_data",
    "pindah_keluar",
    "pindah_datang",
)
_COLLECTIVE_DOCUMENT_LOSS = _compile(
    rf"\b(semua|seluruh)\b.{{0,45}}\b(dokumen|ktp|kk|akta|surat-surat)\b"
    rf".{{0,90}}\b({_DAMAGE_TERMS})\b|"
    rf"\b(dokumen keluarga|dokumen identitas|surat-surat)\b.{{0,70}}\b({_DAMAGE_TERMS})\b"
)
_GENERIC_DOCUMENT_LOSS = _compile(
    rf"\b(identitas|dokumen|dokumen keluarga|dokumen identitas)\b"
    rf".{{0,80}}\b({_DAMAGE_TERMS})\b|"
    rf"\b({_DAMAGE_TERMS})\b.{{0,80}}\b"
    r"(identitas|dokumen|dokumen keluarga|dokumen identitas)\b"
)
_SCREEN_ONLY_LOSS = _compile(
    r"\b(data|nama|dokumen)\b.{0,30}\bhilang\b.{0,25}\b(dari|di)\s+(layar|aplikasi|sistem)\b"
)

# Fire/disaster context requires concrete impact and rejects figurative phrases.
_FIRE_FIGURATIVE = _compile(
    r"\b(harga|semangat|hati|cinta|amarah|emosi|gairah)\b.{0,35}\bterbakar\b|"
    r"\bterbakar\b.{0,35}\b(semangat|hati|cinta|amarah|emosi|gairah)\b|"
    r"\bkebakaran jenggot\b"
)
_FIRE_CONCRETE = _compile(
    r"\b(rumah|bangunan|gedung|kantor|toko|pasar|sekolah|tempat tinggal|kos|kontrakan)\b"
    r".{0,70}\b(terbakar|kebakaran|dilalap api|hangus)\b|"
    r"\b(kebakaran|dilalap api)\b.{0,90}\b(rumah|bangunan|gedung|mengungsi|"
    r"pengungsian|evakuasi|dokumen|ktp|kk|akta|hangus)\b|"
    r"\b(ktp|kk|kartu keluarga|akta(?: kelahiran| kematian)?|dokumen)\b"
    r".{0,100}\b(terbakar|hangus|dilalap api)\b|"
    r"\b(mengungsi|dievakuasi)\b.{0,60}\b(karena|akibat)\b.{0,35}\bkebakaran\b"
)
_NATURAL_DISASTER = _compile(
    r"\b(bencana alam|banjir|tanah longsor|longsor|gempa bumi|gempa|tsunami|"
    r"erupsi|letusan gunung|gunung meletus)\b"
)
_DISASTER_FIGURATIVE = _compile(
    r"\bbanjir\s+(pesanan|order|diskon|promo|pujian|like)\b|\bgempa\s+(politik|pasar)\b"
)
_EVACUATED = _compile(r"\b(mengungsi|pengungsian|dievakuasi|evakuasi darurat)\b")
_EVACUATION_SIMULATION = _compile(r"\b(simulasi|latihan)\s+evakuasi\b")
_DISPLACED = _compile(
    r"\b(terpaksa pindah sementara|sementara tinggal di posko|kehilangan tempat tinggal|"
    r"tinggal di pengungsian|tidak bisa kembali ke rumah|rumah tidak dapat ditempati)\b"
)

# Illness and attendance. Emotional idioms are explicitly excluded.
_ILLNESS_FIGURATIVE = _compile(
    r"\b(sakit hati|sakit kepala memikirkan|sakit melihat|demam panggung|virus komputer)\b"
)
_TEMPORARY_ILLNESS = _compile(
    r"\b(sedang sakit|lagi sakit|kurang sehat|demam|pemulihan|masa pemulihan)\b"
)
_SEVERE_ILLNESS = _compile(
    r"\b(sakit parah|sakit berat|sakit serius|kondisi kritis|perawatan intensif|icu)\b"
)
_HOSPITALIZED = _compile(
    r"\b(rawat inap|opname|masuk rumah sakit|masih di rumah sakit|"
    r"dirawat di rumah sakit|dirawat di klinik)\b"
)
_BEDRIDDEN = _compile(
    r"\b(terbaring|bedridden|hanya bisa berbaring|tidak bisa bangun|tidak dapat bangun)\b"
)
_UNABLE_TO_ATTEND = _compile(
    r"\b(tidak bisa|tidak dapat|belum bisa|sulit)\s+(datang|hadir|ke kantor|ke dukcapil)\b|"
    r"\b(tidak memungkinkan|berhalangan)\s+(datang|hadir)\b"
)
_LIMITED_MOBILITY = _compile(
    r"\b(mobilitas(?: saya|nya)? terbatas|sulit bergerak|sulit berjalan|"
    r"tidak bisa berjalan|gangguan mobilitas)\b"
)
_CAREGIVER = _compile(
    r"\b(dirawat oleh|dibantu oleh|didampingi oleh|pengasuh|caregiver|perawat keluarga|"
    r"anak saya yang mengurus|keluarga yang mengurus)\b"
)

# Disability/accessibility with false-positive protection.
_VISUAL_FIGURATIVE = _compile(r"\b(buta soal|buta tentang|buta aplikasi|buta teknologi)\b")
_VISUAL_IMPAIRMENT = _compile(
    r"\b(tunanetra|gangguan penglihatan|tidak dapat melihat|tidak bisa melihat|"
    r"penglihatan sangat terbatas)\b"
)
_HEARING_IMPAIRMENT = _compile(
    r"\b(tunarungu|gangguan pendengaran|tidak dapat mendengar|tidak bisa mendengar)\b"
)
_SPEECH_IMPAIRMENT = _compile(
    r"\b(tunawicara|gangguan bicara|sulit berbicara|tidak dapat berbicara)\b"
)
_PHYSICAL_DISABILITY = _compile(
    r"\b(disabilitas fisik|difabel fisik|kursi roda|amputasi|kelumpuhan fisik|"
    r"gangguan gerak)\b"
)
_DISABILITY_GENERAL = _compile(r"\b(disabilitas|difabel|penyandang disabilitas)\b")
_COGNITIVE_SUPPORT = _compile(
    r"\b(disabilitas intelektual|keterbatasan kognitif|gangguan kognitif|"
    r"kesulitan memahami instruksi)\b"
)
_COMPANION_NEED = _compile(
    r"\b(butuh pendamping|memerlukan pendamping|perlu didampingi|dengan pendamping)\b"
)
_ACCESSIBILITY_BARRIER = _compile(
    r"\b(aksesibilitas|akses kursi roda|hambatan akses|tidak ada akses ramah disabilitas)\b"
)
_DIGITAL_ACCESSIBILITY = _compile(
    r"\b(sulit menggunakan aplikasi|kesulitan memakai aplikasi|tidak bisa memakai aplikasi|"
    r"kesulitan layanan digital|akses digital sulit|buta aplikasi|buta teknologi)\b"
)

# Elderly/dependent adult.
_ELDERLY = _compile(r"\b(lansia|lanjut usia|usia lanjut|kakek|nenek|orang tua berusia)\b")
_FRAIL_ELDERLY = _compile(r"\b(lansia|kakek|nenek)\b.{0,50}\b(lemah|renta|rapuh|sakit-sakitan)\b")
_ELDERLY_ALONE = _compile(r"\b(lansia|kakek|nenek)\b.{0,50}\b(tinggal sendiri|sendirian)\b")
_ELDERLY_FAMILY_HELP = _compile(
    r"\b(saya anaknya|saya cucunya|keluarga membantu|diwakili keluarga)\b.{0,60}\b"
    r"(lansia|kakek|nenek|orang tua)\b|"
    r"\b(lansia|kakek|nenek|orang tua)\b.{0,60}\b(dibantu|diurus|diwakili)\b"
)
_MEMORY_DIFFICULTY = _compile(
    r"\b(sulit mengingat|lupa status dokumen|tidak ingat dokumennya|sulit menjelaskan)\b"
)

# Pregnancy, birth, and newborn.
_PREGNANCY = _compile(r"\b(hamil|kehamilan|mengandung)\b")
_UNREGISTERED_MARRIAGE = _compile(
    r"\b(menikah|nikah)\b.{0,80}\b(agama|adat|belum tercatat|tidak tercatat|belum catat)\b|"
    r"\b(belum menikah|tanpa nikah|di luar nikah)\b"
)
_IMMINENT_BIRTH = _compile(
    r"\b(akan|mau|segera|menjelang)\s+melahirkan\b|"
    r"\bmelahirkan\b.{0,45}\b(minggu depan|besok|hari ini|beberapa hari|dekat)\b|"
    r"\b(hpl|perkiraan lahir)\b.{0,35}\b(minggu depan|besok|hari ini|dekat)\b"
)
_RECENT_BIRTH = _compile(
    r"\b(baru melahirkan|habis melahirkan|selesai melahirkan|"
    r"setelah melahirkan|pasca melahirkan)\b"
)
_NEWBORN = _compile(r"\b(bayi baru lahir|anak baru lahir|bayi saya baru lahir|newborn)\b")
_MATERNAL_RECOVERY = _compile(
    r"\b(ibu|saya)\b.{0,50}\b(masih dirawat|masih di rumah sakit|masa pemulihan)\b"
    r".{0,35}\b(melahirkan|persalinan)\b|"
    r"\b(setelah melahirkan|pasca melahirkan)\b.{0,45}\b(dirawat|pemulihan)\b"
)
_BIRTH_DOCUMENT_PENDING = _compile(
    r"\b(akta kelahiran|surat kelahiran|dokumen kelahiran)\b.{0,40}\b"
    r"(belum ada|belum terbit|belum dibuat|belum keluar)\b"
)

# Death/bereavement. System/object death idioms are excluded.
_DEATH_FIGURATIVE = _compile(
    r"\b(sistem|aplikasi|mesin|komputer|jaringan|lampu|telepon)\b.{0,25}\b(mati|meninggal)\b"
)
_DEATH_EVENT = _compile(
    r"\b(ayah|ibu|suami|istri|anak|saudara|keluarga|kakek|nenek|orang tua|anggota keluarga)\b"
    r".{0,60}\b(meninggal|wafat|kematian)\b|"
    r"\b(meninggal|wafat|kematian|berduka|masa duka)\b.{0,70}\b"
    r"(ayah|ibu|suami|istri|anak|keluarga|akta|kk|pemakaman|jenazah)\b"
)
_RECENT_DEATH = _compile(r"\b(baru|baru saja|kemarin)\s+(meninggal|wafat)\b")
_UNREGISTERED_DEATH = _compile(
    r"\b(meninggal|wafat|kematian)\b.{0,70}\b(belum dicatat|belum terdaftar|belum dibuatkan akta|"
    r"belum ada akta|belum dilaporkan)\b|"
    r"\b(akta kematian)\b.{0,35}\b(belum ada|belum dibuat|belum terbit)\b"
)
_DECEASED_STILL_LISTED = _compile(
    r"\b(meninggal|wafat|almarhum|almarhumah)\b.{0,70}\b"
    r"(masih ada|masih tercantum|masih terdaftar)\b"
    r".{0,35}\b(kk|kartu keluarga)\b|"
    r"\b(kk|kartu keluarga)\b.{0,55}\b(masih ada|masih tercantum)\b.{0,55}\b"
    r"(meninggal|wafat|almarhum|almarhumah)\b"
)
_DEATH_OUTSIDE_DOMICILE = _compile(
    r"\b(meninggal|wafat)\b.{0,45}\b(di luar daerah|luar kota|beda domisili|daerah lain)\b"
)
_DEATH_ABROAD = _compile(r"\b(meninggal|wafat)\b.{0,45}\b(di luar negeri|luar indonesia)\b")

# Child, guardianship, and caregiver contexts.
_MINOR = _compile(r"\b(anak|bayi|balita|remaja|di bawah umur|belum 17 tahun)\b")
_CHILD_WITHOUT_PARENT = _compile(
    r"\b(anak|bayi)\b.{0,60}\b(tanpa orang tua|orang tua tidak ada|orang tua tidak hadir)\b"
)
_ORPHAN = _compile(r"\b(yatim|piatu|yatim piatu|kedua orang tua meninggal)\b")
_GRANDPARENT_CARE = _compile(
    r"\b(diasuh|dirawat|tinggal dengan)\b.{0,35}\b(kakek|nenek)\b|"
    r"\b(kakek|nenek)\b.{0,45}\b(mengasuh|mengurus dokumen|merawat)\b"
)
_GUARDIAN = _compile(r"\b(wali|perwalian|orang tua asuh|keluarga angkat|pengasuh)\b")
_ABANDONED_CHILD = _compile(r"\b(anak terlantar|bayi terlantar|ditelantarkan)\b")
_PARENT_UNAVAILABLE = _compile(
    r"\b(orang tua|ayah|ibu)\b.{0,55}\b(tidak diketahui|tidak dapat dihubungi|tidak tersedia|"
    r"berada di luar daerah|tidak hadir)\b"
)
_CHILD_OTHER_ADULT = _compile(
    r"\b(dokumen|akta|kk|kia)\b.{0,55}\b(anak|bayi)\b.{0,60}\b"
    r"(diurus oleh|saya yang urus|kakek|nenek|wali|pengasuh)\b"
)

# Violence, safety, and family conflict.
_DOMESTIC_VIOLENCE = _compile(r"\b(kdrt|kekerasan dalam rumah tangga|kekerasan dari pasangan)\b")
_UNSAFE_HOUSEHOLD = _compile(
    r"\b(kabur|melarikan diri|mengungsi)\b.{0,60}\b(rumah tidak aman|pasangan|kekerasan|ancaman)\b|"
    r"\b(takut|tidak aman|terancam)\b.{0,60}\b(kembali ke rumah|pulang|alamat asal)\b"
)
_DOCUMENT_WITHHELD = _compile(
    r"\b(ktp|kk|akta|dokumen|identitas)\b.{0,65}\b(ditahan|disimpan paksa|dikuasai|"
    r"tidak diberikan|disembunyikan)\b.{0,45}\b(pasangan|keluarga|orang lain)?\b|"
    r"\b(pasangan|keluarga|orang lain)\b.{0,60}\b(menahan|menguasai|tidak memberikan)\b"
    r".{0,45}\b(ktp|kk|akta|dokumen|identitas)\b"
)
_FAMILY_CONFLICT = _compile(
    r"\b(konflik keluarga|perselisihan keluarga|berselisih dengan keluarga|masalah keluarga)\b"
    r".{0,80}\b(dokumen|ktp|kk|akta|alamat)?\b"
)
_IMMEDIATE_SAFETY = _compile(
    r"\b(sekarang dalam bahaya|sedang diancam|ancaman langsung|takut dibunuh)\b"
)

# Domicile, migration, and location complexity.
_DIFFERENT_DOMICILE = _compile(
    r"\b(pindah domisili|pindah datang|pindah keluar|surat pindah|daerah lain|beda daerah|"
    r"luar daerah|luar kota|tinggal di tomohon|kk masih di daerah lain|"
    r"domisili berbeda|alamat asal berbeda)\b"
)
_TEMPORARY_RESIDENCE = _compile(
    r"\b(tinggal sementara|sementara tinggal|menumpang sementara|kontrak sementara)\b"
)
_PERMANENT_RELOCATION = _compile(
    r"\b(pindah menetap|menetap di|pindah permanen|pindah selamanya)\b"
)
_OUTSIDE_REGION = _compile(r"\b(berada di luar daerah|kerja di luar daerah|tinggal di luar kota)\b")
_ABROAD = _compile(r"\b(di luar negeri|tinggal di luar negeri|sedang di luar indonesia)\b")
_RETURNING_FROM_ABROAD = _compile(
    r"\b(pulang dari luar negeri|kembali dari luar negeri|kembali ke indonesia)\b"
)
_CANNOT_RETURN_ORIGIN = _compile(
    r"\b(tidak bisa|tidak dapat|belum bisa)\s+kembali\s+ke\s+"
    r"(daerah asal|kota asal|domisili asal)\b"
)
_LOCATION_AMBIGUOUS = _compile(r"\bsaya tinggal di luar\b")

# Housing instability.
_NO_FIXED_ADDRESS = _compile(
    r"\b(tidak punya alamat tetap|tanpa alamat tetap|tidak ada tempat tinggal tetap|"
    r"tunawisma|homeless)\b"
)
_TEMPORARY_SHELTER = _compile(
    r"\b(tinggal di shelter|tinggal di tempat penampungan|tinggal di posko|penampungan sementara)\b"
)
_LIVING_WITH_RELATIVES = _compile(
    r"\b(tinggal dengan|menumpang di)\s+(?:rumah\s+)?"
    r"(saudara|keluarga|kerabat)\b.{0,60}\b"
    r"(tanpa alamat|belum pindah|belum terdaftar)?\b"
)
_UNSTABLE_HOUSING = _compile(
    r"\b(tempat tinggal tidak tetap|sering berpindah tempat|hunian tidak stabil)\b"
)
_INVALID_ADDRESS = _compile(
    r"\b(alamat sudah tidak berlaku|alamat tidak valid|rumah sudah tidak ada)\b"
)

# Literacy, language, and digital barriers.
_LITERACY = _compile(
    r"\b(tidak bisa membaca|sulit membaca|tidak dapat membaca|tidak bisa menulis|sulit menulis)\b"
)
_LANGUAGE = _compile(
    r"\b(tidak lancar bahasa indonesia|sulit bahasa indonesia|tidak paham bahasa indonesia)\b"
)
_NO_DEVICE = _compile(
    r"\b(tidak punya hp|tidak punya ponsel|tidak punya smartphone|tanpa smartphone)\b"
)
_NO_EMAIL = _compile(r"\b(tidak punya email|tidak memiliki email)\b")
_ONLINE_FORM_BARRIER = _compile(
    r"\b(tidak bisa|sulit|bingung)\b.{0,55}\b(formulir online|aplikasi|unggah|upload|pdf|foto)\b|"
    r"\b(formulir online|aplikasi)\b.{0,55}\b(membingungkan|sulit)\b"
)
_ASSISTED_COMMUNICATION = _compile(
    r"\b(dibantu mengetik|orang lain membantu mengetik|saya ketikkan untuk|dibantu mengisi)\b"
)

# Institutional care and restricted mobility.
_DETAINED = _compile(
    r"\b(saya|dia|warga|orang|suami|istri)\b.{0,20}\b"
    r"(sedang ditahan|berada dalam tahanan|ditahan polisi|ditahan aparat)\b|"
    r"\b(dalam tahanan|lapas|rutan|lembaga pemasyarakatan)\b"
)
_REHABILITATION = _compile(r"\b(panti rehabilitasi|pusat rehabilitasi|fasilitas rehabilitasi)\b")
_CARE_INSTITUTION = _compile(
    r"\b(panti asuhan|panti sosial|panti jompo|rumah perawatan|nursing home)\b"
)
_LONG_TERM_CARE = _compile(r"\b(perawatan jangka panjang|dirawat lama|rawat inap jangka panjang)\b")
_CANNOT_LEAVE_INSTITUTION = _compile(
    r"\b(tidak bisa|tidak dapat)\s+keluar\s+dari\s+(lapas|rutan|rumah sakit|panti|institusi)\b"
)

# Identity-data conflict and document inconsistency.
_NAME_MISMATCH = _compile(
    r"\b(nama|ejaan nama)\b.{0,45}\b(berbeda|beda|tidak sama|salah)\b"
    r".{0,35}\b(dokumen|ktp|kk|akta)?\b"
)
_BIRTH_DATE_MISMATCH = _compile(
    r"\b(tanggal lahir|tempat lahir)\b.{0,45}\b(berbeda|beda|tidak sama|salah)\b"
)
_DUPLICATE_IDENTITY = _compile(r"\b(identitas ganda|nik ganda|nik duplikat|data ganda)\b")
_MISMATCHED_NIK = _compile(r"\b(nik)\b.{0,40}\b(berbeda|beda|tidak sama|salah)\b")
_MULTIPLE_FAMILY_RECORDS = _compile(
    r"\b(terdaftar|tercantum)\b.{0,45}\b(dua|lebih dari satu|beberapa)\b"
    r".{0,30}\b(kk|kartu keluarga)\b"
)
_CHILD_NOT_IN_KK = _compile(
    r"\b(anak|bayi)\b.{0,50}\b(belum masuk|belum tercantum|tidak ada)\b"
    r".{0,30}\b(kk|kartu keluarga)\b"
)
_CIVIL_STATUS_MISMATCH = _compile(
    r"\b(status perkawinan|status kawin|jenis kelamin|gender)\b.{0,45}\b"
    r"(berbeda|beda|salah|tidak sesuai)\b"
)
_DOCUMENT_SOURCE_MISMATCH = _compile(
    r"\b(data|biodata|nama|tanggal lahir|tempat lahir)\b.{0,60}\b"
    r"(berbeda|tidak sesuai|tidak sama)\b.{0,50}\b(dokumen|akta|ijazah|surat)\b"
)

# External service dependency.
_EXTERNAL_DEPENDENCY_SPECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("school_dependency", _compile(r"\b(sekolah|pendaftaran sekolah|kuliah|kampus)\b")),
    (
        "healthcare_dependency",
        _compile(r"\b(administrasi rumah sakit|rumah sakit|bpjs|layanan kesehatan|berobat)\b"),
    ),
    (
        "social_assistance_dependency",
        _compile(r"\b(bantuan sosial|bansos|program bantuan|subsidi)\b"),
    ),
    ("employment_dependency", _compile(r"\b(pekerjaan|melamar kerja|kantor|pemberi kerja)\b")),
    ("banking_dependency", _compile(r"\b(bank|perbankan|rekening|pinjaman)\b")),
    ("inheritance_dependency", _compile(r"\b(waris|warisan|ahli waris)\b")),
    (
        "legal_process_dependency",
        _compile(r"\b(pengadilan|proses hukum|sidang|perkara|notaris)\b"),
    ),
)
_EXTERNAL_TIME_SENSITIVE = _compile(
    r"\b(besok|hari ini|minggu depan|segera|mendesak|batas waktu|deadline)\b.{0,100}\b"
    r"(sekolah|rumah sakit|bpjs|pekerjaan|bank|waris|pengadilan|bansos|pernikahan|perjalanan)\b|"
    r"\b(dokumen|ktp|kk|akta)\b.{0,80}\b(dibutuhkan|diperlukan)\b.{0,80}\b"
    r"(sekolah|rumah sakit|bpjs|pekerjaan|bank|waris|pengadilan|bansos|pernikahan|perjalanan)\b"
)

_DISTRESS = _compile(
    r"\b(bingung|cemas|khawatir|panik|takut|tidak tahu|nyanda tahu|susah sekali|tolong bantu)\b"
)
_URGENT_DEADLINE = _compile(
    r"\b(besok dibutuhkan|segera dibutuhkan|mendesak|deadline|batas waktu|"
    r"minggu depan dibutuhkan|hari ini dibutuhkan)\b"
)
_VULNERABLE_FAMILY = _compile(
    r"\b(orang tua tunggal|tidak ada pendamping|keluarga rentan|tidak punya keluarga|"
    r"ditinggalkan pasangan)\b"
)


def _real_fire(message: str) -> bool:
    if not _FIRE_CONCRETE.search(message):
        return False
    if _FIRE_FIGURATIVE.search(message) and not re.search(
        r"\b(dokumen|ktp|kk|akta|mengungsi|evakuasi|hangus|dilalap api|"
        r"rumah (saya|kami)|bangunan (saya|kami))\b",
        message,
        re.I,
    ):
        return False
    return True


def _natural_disaster(message: str) -> bool:
    return bool(_NATURAL_DISASTER.search(message) and not _DISASTER_FIGURATIVE.search(message))


def _illness_is_real(message: str) -> bool:
    if _ILLNESS_FIGURATIVE.search(message):
        return bool(
            _SEVERE_ILLNESS.search(message)
            or _HOSPITALIZED.search(message)
            or _BEDRIDDEN.search(message)
        )
    return bool(
        _TEMPORARY_ILLNESS.search(message)
        or _SEVERE_ILLNESS.search(message)
        or _HOSPITALIZED.search(message)
        or _BEDRIDDEN.search(message)
    )


def _lost_documents(message: str) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    if _SCREEN_ONLY_LOSS.search(message):
        return (), (), False
    tags: list[str] = []
    services: list[str] = []
    for tag, service, document_pattern in _DOCUMENT_SPECS:
        pattern = re.compile(
            rf"\b(?:{document_pattern})\b.{{0,130}}\b(?:{_DAMAGE_TERMS})\b|"
            rf"\b(?:{_DAMAGE_TERMS})\b.{{0,130}}\b(?:{document_pattern})\b",
            re.I,
        )
        if pattern.search(message):
            tags.append(tag)
            services.append(service)
    collective = bool(_COLLECTIVE_DOCUMENT_LOSS.search(message))
    return _dedupe(tags), _dedupe(services), collective


def _ordered_services(services: Iterable[str]) -> tuple[str, ...]:
    selected = set(services)
    return tuple(service for service in _SERVICE_ORDER if service in selected)


def _add_tags(tags: list[str], *values: str) -> None:
    tags.extend(value for value in values if value)


class HumanContextAnalyzer:
    """Understand human circumstances without profiling or administrative judgment."""

    def __init__(self, urgency_detector: UrgencyDetector | None = None) -> None:
        self.urgency_detector = urgency_detector or UrgencyDetector()

    def analyze(self, message: str) -> HumanContext:
        normalized = " ".join(message.split())
        tags: list[str] = []
        priority: list[str] = []
        guidance: list[str] = []
        clarification: list[str] = []
        accessibility: list[str] = []
        safety_flags: list[str] = []
        empathy_mode = "none"
        empathy_text: str | None = None
        sensitivity = "normal"
        privacy_risk = "low"
        requires_human_verification = False

        lost_tags, lost_services, collective_document_loss = _lost_documents(normalized)
        _add_tags(tags, *lost_tags)
        generic_document_loss = bool(
            _GENERIC_DOCUMENT_LOSS.search(normalized) and not _SCREEN_ONLY_LOSS.search(normalized)
        )
        if lost_services or generic_document_loss or collective_document_loss:
            _add_tags(tags, "lost_identity_document", "lost_identity")
        if len(lost_services) >= 2 or collective_document_loss:
            _add_tags(tags, "multiple_documents_lost")

        # Group 01: fire, disaster, evacuation, and displacement.
        fire = _real_fire(normalized)
        natural_disaster = _natural_disaster(normalized)
        evacuated = bool(
            _EVACUATED.search(normalized) and not _EVACUATION_SIMULATION.search(normalized)
        )
        displaced = bool(
            _DISPLACED.search(normalized) or (evacuated and (fire or natural_disaster))
        )
        if fire:
            _add_tags(tags, "fire_incident", "disaster_affected")
        elif natural_disaster:
            _add_tags(tags, "disaster_affected")
        if evacuated and (fire or natural_disaster):
            _add_tags(tags, "evacuated")
        if displaced:
            _add_tags(tags, "displaced_resident")
        if (fire or natural_disaster) and "lost_identity_document" in tags:
            _add_tags(tags, "emergency_document_recovery")
        if fire or natural_disaster:
            sensitivity = "high"
            privacy_risk = _raise_level(privacy_risk, "medium", _RISK_ORDER)
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            incident = "kebakaran" if fire else "bencana"
            empathy_text = (
                f"Saya turut prihatin atas {incident} yang Anda alami. Keselamatan dan bantuan "
                "darurat perlu dibedakan dari layanan administrasi Dukcapil; saya akan membantu "
                "mengurutkan pemulihan dokumen berdasarkan sumber resmi yang tersedia."
            )
            priority.extend(_ordered_services(lost_services))
            guidance.extend(
                (
                    "bedakan bantuan darurat dari administrasi Dukcapil",
                    "prioritaskan pemulihan identitas tanpa mengklaim urutan wajib",
                    "sebutkan penggantian dokumen terkait hanya sebagai kemungkinan",
                    "jangan menjanjikan percepatan penerbitan atau layanan khusus",
                    "gunakan hanya persyaratan yang didukung Knowledge Base",
                    "arahkan ke petugas berwenang bila bukti atau yurisdiksi belum jelas",
                )
            )
            if not lost_services:
                clarification.append("jenis_dokumen_hilang_atau_rusak")
            if displaced:
                clarification.append("status_tempat_tinggal_sementara")
            if "emergency_document_recovery" in tags:
                clarification.append("kebutuhan_dokumen_paling_mendesak")
            requires_human_verification = displaced

        # Group 02: illness, hospitalization, and inability to attend.
        real_illness = _illness_is_real(normalized)
        if real_illness and _TEMPORARY_ILLNESS.search(normalized):
            _add_tags(tags, "temporary_illness")
        if _SEVERE_ILLNESS.search(normalized):
            _add_tags(tags, "severe_illness")
        if _HOSPITALIZED.search(normalized):
            _add_tags(tags, "hospitalized")
        if _BEDRIDDEN.search(normalized):
            _add_tags(tags, "bedridden")
        if _UNABLE_TO_ATTEND.search(normalized):
            _add_tags(tags, "unable_to_attend_in_person")
        if _LIMITED_MOBILITY.search(normalized):
            _add_tags(tags, "accessibility_need", "physical_disability")
            accessibility.append("limited_mobility")
        if _CAREGIVER.search(normalized):
            _add_tags(tags, "caregiver_required")
            accessibility.append("caregiver_support")
        illness_tags = {
            "temporary_illness",
            "severe_illness",
            "hospitalized",
            "bedridden",
            "unable_to_attend_in_person",
        }
        if illness_tags.intersection(tags):
            sensitivity = "medium" if sensitivity == "normal" else sensitivity
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya memahami kondisi kesehatan dapat membatasi kehadiran langsung. Saya akan "
                "menjelaskan pilihan administrasi secara hati-hati tanpa meminta diagnosis atau "
                "menjanjikan layanan khusus."
            )
            guidance.extend(
                (
                    "jangan meminta diagnosis atau rincian medis",
                    "jangan memberikan nasihat medis",
                    "sebutkan perwakilan, layanan bergerak, atau kanal alternatif "
                    "hanya jika KB mendukung",
                    "jangan menjanjikan layanan rumah atau prioritas khusus",
                )
            )
            if "unable_to_attend_in_person" in tags or "bedridden" in tags:
                clarification.append("kemampuan_hadir_dan_bantuan_yang_tersedia")
                requires_human_verification = True

        # Group 03: disability and accessibility.
        if _DISABILITY_GENERAL.search(normalized):
            _add_tags(tags, "disability", "accessibility_need")
        if _PHYSICAL_DISABILITY.search(normalized):
            _add_tags(tags, "disability", "physical_disability", "accessibility_need")
            accessibility.append("mobility_access")
        if _VISUAL_IMPAIRMENT.search(normalized) and not _VISUAL_FIGURATIVE.search(normalized):
            _add_tags(tags, "disability", "visual_impairment", "accessibility_need")
            accessibility.append("visual_access")
        if _HEARING_IMPAIRMENT.search(normalized):
            _add_tags(tags, "disability", "hearing_impairment", "accessibility_need")
            accessibility.append("hearing_access")
        if _SPEECH_IMPAIRMENT.search(normalized):
            _add_tags(tags, "disability", "accessibility_need")
            accessibility.append("communication_support")
        if _COGNITIVE_SUPPORT.search(normalized):
            _add_tags(tags, "disability", "cognitive_support_need", "accessibility_need")
            accessibility.append("cognitive_support")
        if _COMPANION_NEED.search(normalized):
            _add_tags(tags, "companion_required", "accessibility_need")
            accessibility.append("companion_support")
        if _ACCESSIBILITY_BARRIER.search(normalized):
            _add_tags(tags, "accessibility_need")
            accessibility.append("physical_accessibility")
        if _DIGITAL_ACCESSIBILITY.search(normalized):
            _add_tags(tags, "digital_accessibility_barrier", "accessibility_need")
            accessibility.append("digital_assistance")
        if "accessibility_need" in tags or "disability" in tags:
            sensitivity = "medium" if sensitivity == "normal" else sensitivity
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya akan menyampaikan langkahnya secara jelas dan berurutan. Pilihan bantuan "
                "atau akses khusus hanya dapat disebutkan bila didukung sumber resmi."
            )
            guidance.extend(
                (
                    "gunakan bahasa hormat dan tidak merendahkan",
                    "gunakan instruksi singkat dan berurutan",
                    "jangan mengasumsikan ketidakmampuan atau ketidakcakapan hukum",
                    "tawarkan dukungan akses hanya bila Knowledge Base mendukung",
                )
            )

        # Group 04: elderly and dependent adult.
        if _ELDERLY.search(normalized):
            _add_tags(tags, "elderly")
        if _FRAIL_ELDERLY.search(normalized):
            _add_tags(tags, "frail_elderly", "dependent_adult")
        if _ELDERLY_ALONE.search(normalized):
            _add_tags(tags, "dependent_adult", "family_assistance_needed")
        if _ELDERLY_FAMILY_HELP.search(normalized):
            _add_tags(tags, "family_assistance_needed")
        if _MEMORY_DIFFICULTY.search(normalized) and "elderly" in tags:
            _add_tags(tags, "dependent_adult", "family_assistance_needed")
            accessibility.append("memory_support")
        if "elderly" in tags:
            sensitivity = "medium" if sensitivity == "normal" else sensitivity
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            if "lost_identity_document" in tags:
                empathy_text = empathy_text or (
                    "Saya memahami pengurusan dokumen yang hilang dapat terasa menyulitkan bagi "
                    "lansia; langkahnya akan saya susun singkat dan bertahap."
                )
            else:
                empathy_text = empathy_text or (
                    "Saya akan menjelaskan langkahnya secara singkat dan mudah diikuti."
                )
            guidance.extend(
                (
                    "gunakan langkah singkat dan jelas",
                    "jangan menganggap keluarga otomatis berhak mewakili",
                    "perlindungan data lansia tetap berlaku",
                )
            )
            if "family_assistance_needed" in tags:
                requires_human_verification = True

        # Group 05: pregnancy, birth, and newborn.
        if _PREGNANCY.search(normalized):
            _add_tags(tags, "pregnancy")
        if _UNREGISTERED_MARRIAGE.search(normalized):
            _add_tags(tags, "unregistered_marriage")
        if _IMMINENT_BIRTH.search(normalized):
            _add_tags(tags, "imminent_birth")
        if _RECENT_BIRTH.search(normalized):
            _add_tags(tags, "recent_birth")
        if _NEWBORN.search(normalized):
            _add_tags(tags, "newborn_child")
        if _MATERNAL_RECOVERY.search(normalized):
            _add_tags(tags, "maternal_recovery")
        if _BIRTH_DOCUMENT_PENDING.search(normalized):
            _add_tags(tags, "birth_document_pending")
        pregnancy_related = bool(
            {"pregnancy", "imminent_birth", "recent_birth", "newborn_child"}.intersection(tags)
        )
        if pregnancy_related:
            if "pregnancy" in tags and "unregistered_marriage" in tags:
                _add_tags(tags, "unmarried_pregnancy")
            if "newborn_child" in tags or "recent_birth" in tags:
                _add_tags(tags, "newborn_parent")
            sensitivity = (
                "high"
                if "unregistered_marriage" in tags
                else max(sensitivity, "medium", key=("normal", "medium", "high").index)
            )
            privacy_risk = _raise_level(privacy_risk, "medium", _RISK_ORDER)
            empathy_mode = _raise_level(
                empathy_mode,
                "sensitive" if "unregistered_marriage" in tags else "supportive",
                _EMPATHY_ORDER,
            )
            if "imminent_birth" in tags:
                empathy_text = (
                    "Saya memahami waktunya sudah dekat. Kebutuhan kesehatan tetap terpisah dari "
                    "administrasi; untuk dokumen, mari kita prioritaskan langkah yang didukung "
                    "sumber resmi tanpa menjanjikan percepatan."
                )
            elif "unregistered_marriage" in tags:
                empathy_text = (
                    "Saya memahami situasi ini bersifat pribadi dan sensitif; informasi akan "
                    "disampaikan tanpa menghakimi dan berfokus pada layanan yang diperlukan."
                )
            elif "newborn_child" in tags or "recent_birth" in tags:
                empathy_text = (
                    "Selamat atas kelahiran anak Anda; mari kita susun layanan administrasi "
                    "yang relevan secara bertahap."
                )
            else:
                empathy_text = empathy_text or (
                    "Saya memahami kehamilan dapat membuat persiapan administrasi terasa lebih "
                    "mendesak; mari kita susun kebutuhan yang paling penting."
                )
            priority.extend(("akta_kelahiran", "kartu_keluarga"))
            if "newborn_child" in tags or "recent_birth" in tags:
                priority.append("kia")
            guidance.extend(
                (
                    "gunakan bahasa netral, nonmedis, dan tidak menghakimi",
                    "bedakan prioritas kesehatan dari administrasi",
                    "jangan menyimpulkan status hukum keluarga",
                    "jangan menjanjikan percepatan layanan",
                    "hubungan akta kelahiran dan KK harus evidence-aware",
                )
            )
            if "unregistered_marriage" in tags:
                clarification.append("status_pencatatan_perkawinan")
                requires_human_verification = True
            if "imminent_birth" in tags:
                clarification.append("dokumen_kelahiran_dan_domisili")

        # Group 06: death and bereavement.
        death = bool(_DEATH_EVENT.search(normalized) and not _DEATH_FIGURATIVE.search(normalized))
        if death:
            _add_tags(tags, "bereavement")
        if death and _RECENT_DEATH.search(normalized):
            _add_tags(tags, "recent_death")
        if death and _UNREGISTERED_DEATH.search(normalized):
            _add_tags(tags, "unregistered_death")
        if death and _DECEASED_STILL_LISTED.search(normalized):
            _add_tags(tags, "deceased_still_in_family_record")
        if death and _DEATH_OUTSIDE_DOMICILE.search(normalized):
            _add_tags(tags, "death_outside_domicile")
        if death and _DEATH_ABROAD.search(normalized):
            _add_tags(tags, "death_abroad")
        if death:
            sensitivity = "high"
            privacy_risk = _raise_level(privacy_risk, "medium", _RISK_ORDER)
            empathy_mode = _raise_level(empathy_mode, "sensitive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya memahami keluarga sedang menghadapi masa duka; mari kita susun langkah "
                "administrasinya dengan tenang dan jelas."
            )
            priority = ["akta_kematian", "kartu_keluarga", *priority]
            guidance.extend(
                (
                    "gunakan pengakuan duka singkat dan hormat",
                    "jangan menyatakan urutan wajib tanpa sumber",
                    "perubahan KK disebut sebagai hubungan yang mungkin relevan",
                )
            )
            if "unregistered_death" not in tags:
                clarification.append("status_pencatatan_kematian")
            if "death_outside_domicile" in tags or "death_abroad" in tags:
                requires_human_verification = True

        # Group 07: child, guardianship, and caregiver.
        if _MINOR.search(normalized):
            _add_tags(tags, "minor_or_child", "minor")
        if _CHILD_WITHOUT_PARENT.search(normalized):
            _add_tags(tags, "child_without_parent_present", "child_protection_sensitive")
        if _ORPHAN.search(normalized):
            _add_tags(tags, "orphan_context", "parent_unavailable", "child_protection_sensitive")
        if _GRANDPARENT_CARE.search(normalized):
            _add_tags(tags, "caregiver_context", "guardian_context", "child_protection_sensitive")
        if _GUARDIAN.search(normalized):
            _add_tags(tags, "guardian_context", "caregiver_context")
        if _ABANDONED_CHILD.search(normalized):
            _add_tags(tags, "child_protection_sensitive", "parent_unavailable")
        if _PARENT_UNAVAILABLE.search(normalized):
            _add_tags(tags, "parent_unavailable", "child_protection_sensitive")
        if _CHILD_OTHER_ADULT.search(normalized):
            _add_tags(tags, "caregiver_context", "child_protection_sensitive")
        if "child_protection_sensitive" in tags or "guardian_context" in tags:
            sensitivity = "high"
            privacy_risk = _raise_level(privacy_risk, "high", _RISK_ORDER)
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya akan membatasi pertanyaan pada informasi yang benar-benar diperlukan dan "
                "tidak menganggap status wali atau pengasuh sudah sah secara hukum."
            )
            guidance.extend(
                (
                    "bedakan pengasuh dari wali yang sah",
                    "jangan meminta rincian sensitif anak",
                    "jangan membuat kesimpulan hukum perwalian",
                    "rujuk petugas berwenang bila status wali belum jelas",
                )
            )
            clarification.append("hubungan_pengurus_dengan_anak")
            requires_human_verification = True

        # Group 08: violence, safety, and family conflict.
        if _DOMESTIC_VIOLENCE.search(normalized):
            _add_tags(tags, "safety_risk", "domestic_violence_context", "unsafe_household")
        if _UNSAFE_HOUSEHOLD.search(normalized):
            _add_tags(tags, "safety_risk", "unsafe_household")
        if _DOCUMENT_WITHHELD.search(normalized):
            _add_tags(tags, "document_withheld", "family_conflict", "privacy_sensitive")
        if _FAMILY_CONFLICT.search(normalized):
            _add_tags(tags, "family_conflict", "privacy_sensitive")
        if _IMMEDIATE_SAFETY.search(normalized):
            _add_tags(tags, "safety_risk")
            safety_flags.append("immediate_safety_concern")
        if {"safety_risk", "document_withheld", "family_conflict"}.intersection(tags):
            sensitivity = "high"
            privacy_risk = "high"
            empathy_mode = _raise_level(empathy_mode, "sensitive", _EMPATHY_ORDER)
            empathy_text = (
                "Saya memahami keamanan dan privasi Anda perlu dijaga. Saya tidak akan meminta "
                "rincian traumatis, alamat lengkap, atau identitas lengkap; panduan Dukcapil "
                "akan dibatasi pada sumber resmi yang tersedia."
            )
            safety_flags.extend(
                tag
                for tag in ("safety_risk", "unsafe_household", "document_withheld")
                if tag in tags
            )
            guidance.extend(
                (
                    "jangan meminta rincian traumatis atau menyelidiki tuduhan",
                    "jangan menyarankan konfrontasi",
                    "jangan menampilkan alamat atau pengenal pribadi",
                    "pisahkan bahaya langsung dari layanan administrasi Dukcapil",
                    "jangan mengarang nomor kontak darurat lokal",
                )
            )
            requires_human_verification = True

        # Group 09: domicile, migration, and location complexity.
        if _DIFFERENT_DOMICILE.search(normalized):
            _add_tags(tags, "different_domicile", "relocation")
        if _TEMPORARY_RESIDENCE.search(normalized):
            _add_tags(tags, "temporary_residence", "different_domicile")
        if _PERMANENT_RELOCATION.search(normalized):
            _add_tags(tags, "permanent_relocation", "different_domicile", "relocation")
        if _OUTSIDE_REGION.search(normalized):
            _add_tags(tags, "outside_region", "different_domicile")
        if _ABROAD.search(normalized):
            _add_tags(tags, "abroad", "different_domicile")
        if _RETURNING_FROM_ABROAD.search(normalized):
            _add_tags(tags, "returning_from_abroad", "different_domicile")
        if _CANNOT_RETURN_ORIGIN.search(normalized):
            _add_tags(tags, "jurisdiction_uncertain", "different_domicile")
        if _LOCATION_AMBIGUOUS.search(normalized) and "different_domicile" not in tags:
            _add_tags(tags, "jurisdiction_uncertain")
            clarification.append("lokasi_tinggal_yang_dimaksud")
        if "different_domicile" in tags or "jurisdiction_uncertain" in tags:
            empathy_mode = _raise_level(empathy_mode, "light", _EMPATHY_ORDER)
            if "relocation" in tags:
                empathy_text = empathy_text or (
                    "Saya memahami perpindahan domisili dapat melibatkan beberapa layanan; mari "
                    "kita pisahkan setiap kebutuhannya tanpa mengasumsikan tempat pengurusannya."
                )
                priority.extend(("pindah_keluar", "pindah_datang", "kartu_keluarga"))
            else:
                empathy_text = empathy_text or (
                    "Saya memahami lokasi tempat tinggal dan domisili terdaftar dapat memengaruhi "
                    "jalur layanan; saya tidak akan mengasumsikan tempat pengurusannya."
                )
            guidance.extend(
                (
                    "bedakan tinggal sementara dari pindah menetap",
                    "hindari asumsi yurisdiksi atau lokasi layanan",
                    "gunakan metadata yurisdiksi dan Knowledge Base",
                )
            )
            clarification.append("jenis_domisili_dan_daerah_asal_tujuan")
            if "abroad" in tags or "jurisdiction_uncertain" in tags:
                requires_human_verification = True

        # Group 10: no fixed address and housing instability.
        if _NO_FIXED_ADDRESS.search(normalized):
            _add_tags(tags, "no_fixed_address", "housing_instability", "address_uncertain")
        if _TEMPORARY_SHELTER.search(normalized):
            _add_tags(tags, "temporary_shelter", "housing_instability", "address_uncertain")
        if _LIVING_WITH_RELATIVES.search(normalized):
            _add_tags(tags, "housing_instability", "address_uncertain")
        if _UNSTABLE_HOUSING.search(normalized):
            _add_tags(tags, "housing_instability", "address_uncertain")
        if _INVALID_ADDRESS.search(normalized):
            _add_tags(tags, "address_uncertain")
        if {"no_fixed_address", "housing_instability", "temporary_shelter"}.intersection(tags):
            sensitivity = "high"
            privacy_risk = _raise_level(privacy_risk, "medium", _RISK_ORDER)
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya akan menggunakan bahasa yang netral dan tidak mengasumsikan kesalahan. "
                "Status alamat perlu diklarifikasi tanpa mengarang persyaratan domisili."
            )
            guidance.extend(
                (
                    "jangan mengasumsikan kesalahan karena kondisi hunian",
                    "jangan mengarang persyaratan alamat",
                    "gunakan verifikasi petugas ketika bukti KB terbatas",
                )
            )
            clarification.append("status_alamat_saat_ini")
            requires_human_verification = True

        # Group 11: literacy, language, and digital barriers.
        if _LITERACY.search(normalized):
            _add_tags(tags, "literacy_support_needed", "accessibility_need")
            accessibility.append("literacy_support")
        if _LANGUAGE.search(normalized):
            _add_tags(tags, "language_support_needed", "accessibility_need")
            accessibility.append("language_support")
        if _NO_DEVICE.search(normalized):
            _add_tags(tags, "no_device_access", "digital_literacy_barrier", "accessibility_need")
            accessibility.append("non_digital_access")
        if _NO_EMAIL.search(normalized):
            _add_tags(tags, "digital_literacy_barrier", "accessibility_need")
            accessibility.append("no_email_access")
        if _ONLINE_FORM_BARRIER.search(normalized) or _VISUAL_FIGURATIVE.search(normalized):
            _add_tags(tags, "digital_literacy_barrier", "accessibility_need")
            accessibility.append("digital_assistance")
        if _ASSISTED_COMMUNICATION.search(normalized):
            _add_tags(tags, "assisted_communication", "accessibility_need")
            accessibility.append("assisted_communication")
        communication_barriers = {
            "literacy_support_needed",
            "language_support_needed",
            "digital_literacy_barrier",
        }
        if communication_barriers.intersection(tags):
            sensitivity = "medium" if sensitivity == "normal" else sensitivity
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya akan menggunakan langkah bernomor dan bahasa sederhana tanpa menganggap "
                "pengguna atau orang yang membantu otomatis memiliki kewenangan hukum."
            )
            guidance.extend(
                (
                    "gunakan kalimat sederhana dan langkah bernomor",
                    "hindari jargon dan jangan mempermalukan pengguna",
                    "jangan mewajibkan kanal digital kecuali sumber resmi menyatakannya",
                    "opsi luring atau bantuan hanya disebut bila KB mendukung",
                )
            )

        # Group 12: detention, institutional care, and restricted mobility.
        if _DETAINED.search(normalized):
            _add_tags(tags, "institutionalized", "detained", "restricted_mobility")
        if _REHABILITATION.search(normalized) or _CARE_INSTITUTION.search(normalized):
            _add_tags(tags, "institutionalized", "restricted_mobility")
        if _LONG_TERM_CARE.search(normalized):
            _add_tags(tags, "institutionalized", "restricted_mobility", "long_term_care")
        if _CANNOT_LEAVE_INSTITUTION.search(normalized):
            _add_tags(tags, "restricted_mobility")
        if "institutionalized" in tags or "restricted_mobility" in tags:
            sensitivity = "high"
            privacy_risk = _raise_level(privacy_risk, "medium", _RISK_ORDER)
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya akan menggunakan bahasa netral. Prosedur khusus, perwakilan, atau layanan "
                "institusional hanya dapat disebutkan bila didukung sumber resmi."
            )
            guidance.extend(
                (
                    "jangan menyimpulkan kesalahan atau status hukum",
                    "jangan menjanjikan perwakilan atau layanan institusional",
                    "setiap prosedur khusus memerlukan bukti KB dan verifikasi petugas",
                )
            )
            clarification.append("batasan_kehadiran_dan_pihak_yang_membantu")
            requires_human_verification = True

        # Group 13: identity-data conflict and document inconsistency.
        identity_conflict = False
        family_record_conflict = False
        if _NAME_MISMATCH.search(normalized) or _BIRTH_DATE_MISMATCH.search(normalized):
            _add_tags(tags, "identity_data_mismatch", "biodata_conflict")
            identity_conflict = True
        if _DUPLICATE_IDENTITY.search(normalized) or _MISMATCHED_NIK.search(normalized):
            _add_tags(tags, "possible_duplicate_record", "identity_data_mismatch")
            identity_conflict = True
        if _MULTIPLE_FAMILY_RECORDS.search(normalized) or _CHILD_NOT_IN_KK.search(normalized):
            _add_tags(tags, "family_record_mismatch")
            family_record_conflict = True
        if _DECEASED_STILL_LISTED.search(normalized):
            _add_tags(tags, "family_record_mismatch")
            family_record_conflict = True
        if _CIVIL_STATUS_MISMATCH.search(normalized):
            _add_tags(tags, "civil_status_mismatch", "biodata_conflict")
            identity_conflict = True
        if _DOCUMENT_SOURCE_MISMATCH.search(normalized):
            _add_tags(tags, "identity_data_mismatch", "biodata_conflict")
            identity_conflict = True
        if identity_conflict or family_record_conflict:
            _add_tags(tags, "manual_verification_required")
            sensitivity = "high"
            privacy_risk = "high"
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya memahami ada perbedaan data antar dokumen. Sistem tidak dapat menentukan "
                "data mana yang sah; bukti perlu diperiksa oleh petugas berwenang."
            )
            if identity_conflict:
                priority.insert(0, "perubahan_data")
            guidance.extend(
                (
                    "jangan menentukan data mana yang sah",
                    "jangan menyarankan perubahan bukti",
                    "minta klarifikasi non-sensitif saja",
                    "jangan menampilkan nomor identitas lengkap",
                )
            )
            clarification.append("jenis_perbedaan_data_dan_dokumen_yang_terdampak")
            requires_human_verification = True

        # Group 14: external-service dependency.
        external_tags = [
            tag for tag, pattern in _EXTERNAL_DEPENDENCY_SPECS if pattern.search(normalized)
        ]
        _add_tags(tags, *external_tags)
        if _EXTERNAL_TIME_SENSITIVE.search(normalized):
            _add_tags(tags, "time_sensitive_external_dependency")
        if external_tags or "time_sensitive_external_dependency" in tags:
            guidance.extend(
                (
                    "fokus pada dokumen Dukcapil yang diminta",
                    "jangan memberi prosedur layanan eksternal di luar KB",
                    "deadline eksternal tidak berarti percepatan Dukcapil dijamin",
                )
            )
            if "time_sensitive_external_dependency" in tags:
                clarification.append("batas_waktu_dan_dokumen_yang_dibutuhkan")

        if _DISTRESS.search(normalized):
            _add_tags(tags, "distress_or_confusion")
            empathy_mode = _raise_level(empathy_mode, "supportive", _EMPATHY_ORDER)
            empathy_text = empathy_text or (
                "Saya memahami situasinya membingungkan; mari kita urutkan kebutuhan yang paling "
                "penting terlebih dahulu."
            )
            guidance.append("gunakan langkah bernomor dan hindari istilah teknis")
        if _URGENT_DEADLINE.search(normalized):
            _add_tags(tags, "urgent_deadline")
        if _VULNERABLE_FAMILY.search(normalized):
            _add_tags(tags, "vulnerable_family")

        # Preserve explicit document recovery priorities.
        priority = [*_ordered_services(lost_services), *priority]
        if "lost_ktp" in tags:
            priority.insert(0, "ktp_el")
        if "lost_family_card" in tags and "kartu_keluarga" not in priority:
            priority.insert(0, "kartu_keluarga")
        if "lost_identity_document" in tags:
            clarification.append("jenis_dokumen_hilang_rusak_atau_koreksi")
        if "imminent_birth" in tags:
            birth_priority = ("akta_kelahiran", "kartu_keluarga")
            priority = [*birth_priority, *(item for item in priority if item not in birth_priority)]

        # Group 15: multiple vulnerabilities. Count conceptual groups, not every tag.
        group_markers = {
            "disaster": {"fire_incident", "disaster_affected", "displaced_resident"},
            "illness": illness_tags,
            "accessibility": {
                "disability",
                "physical_disability",
                "visual_impairment",
                "hearing_impairment",
                "cognitive_support_need",
            },
            "elderly": {"elderly", "frail_elderly", "dependent_adult"},
            "pregnancy_birth": {"pregnancy", "imminent_birth", "newborn_child", "recent_birth"},
            "bereavement": {"bereavement", "recent_death"},
            "child": {"child_protection_sensitive", "guardian_context", "orphan_context"},
            "safety": {"safety_risk", "document_withheld", "unsafe_household"},
            "domicile": {"different_domicile", "jurisdiction_uncertain"},
            "housing": {"no_fixed_address", "housing_instability"},
            "literacy": {"literacy_support_needed", "digital_literacy_barrier"},
            "institution": {"institutionalized", "restricted_mobility"},
            "identity_conflict": {"identity_data_mismatch", "biodata_conflict"},
            "document_loss": {"lost_identity_document", "multiple_documents_lost"},
        }
        matched_groups = {
            name for name, markers in group_markers.items() if markers.intersection(tags)
        }
        if len(matched_groups) >= 2:
            _add_tags(tags, "multiple_sensitive_circumstances")
            sensitivity = "high"
            privacy_risk = _raise_level(
                privacy_risk,
                "high" if len(matched_groups) >= 4 else "medium",
                _RISK_ORDER,
            )
            guidance.append("prioritaskan konteks paling mendesak tanpa menghapus konteks lain")

        tags_tuple = _dedupe(tags)
        urgency = self.urgency_detector.assess(normalized, context_tags=tags_tuple)
        if urgency.level == "high":
            guidance.append("urgensi tidak memberi kewenangan menjanjikan percepatan")

        return HumanContext(
            tags=tags_tuple,
            sensitivity=sensitivity,
            urgency=urgency.level,
            empathy_mode=empathy_mode,
            empathy_text=empathy_text,
            priority_hints=_dedupe(priority),
            response_guidance=_dedupe(guidance),
            privacy_risk=privacy_risk,
            requires_clarification=bool(clarification),
            clarification_reasons=_dedupe((*clarification, *urgency.evidence)),
            accessibility_needs=_dedupe(accessibility),
            safety_flags=_dedupe(safety_flags),
            requires_human_verification=requires_human_verification,
        )
