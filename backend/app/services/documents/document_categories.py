from dataclasses import dataclass

from app.core.exceptions import document_error

AUTHORITY_RANK = {
    "uu": 1,
    "pp_perpres": 2,
    "permendagri": 3,
    "se_kep_dirjen": 4,
    "perda_perwako": 5,
    "sop": 6,
    "buku_saku": 7,
    "faq_pendukung": 8,
}

CATEGORY_LABELS = {
    "uu": "Undang-Undang",
    "pp_perpres": "PP / Perpres",
    "permendagri": "Permendagri",
    "se_kep_dirjen": "SE / Keputusan Dirjen Dukcapil",
    "perda_perwako": "Perda / Perwako",
    "sop": "SOP Dukcapil",
    "buku_saku": "Buku Saku Dukcapil",
    "faq_pendukung": "FAQ Resmi / Dokumen Pendukung",
}

ALIASES = {
    **{key.casefold(): key for key in AUTHORITY_RANK},
    **{label.casefold(): key for key, label in CATEGORY_LABELS.items()},
    "sop pelayanan": "sop",
    "persyaratan dokumen": "faq_pendukung",
    "faq resmi": "faq_pendukung",
    "surat edaran": "se_kep_dirjen",
    "peraturan daerah": "perda_perwako",
}

NATIONAL = {"uu", "pp_perpres", "permendagri", "se_kep_dirjen"}


@dataclass(frozen=True, slots=True)
class CategoryMetadata:
    code: str
    label: str
    authority_rank: int
    jurisdiction: str


def normalize_category(value: str) -> CategoryMetadata:
    normalized = " ".join(value.strip().split()).casefold()
    code = ALIASES.get(normalized)
    if code is None:
        raise document_error(
            "VALIDATION_ERROR",
            "Kategori dokumen tidak didukung.",
            422,
        )
    return CategoryMetadata(
        code=code,
        label=CATEGORY_LABELS[code],
        authority_rank=AUTHORITY_RANK[code],
        jurisdiction="national" if code in NATIONAL else "city",
    )
