from __future__ import annotations

import re
from dataclasses import dataclass

NATIONAL_ID_PATTERN = re.compile(r"(?<!\d)(?:\d[\s.\-]?){16}(?!\d)")
CREDENTIAL_PATTERN = re.compile(
    r"\b(otp|pin|password|kata sandi|"
    r"kode verifikasi|token login)\b"
    r"\s*[:=]?\s*([A-Za-z0-9@#$%._-]{4,})",
    re.I,
)
PROMPT_INJECTION_PATTERN = re.compile(
    r"abaikan (semua |seluruh )?instruksi|tampilkan system prompt|bocorkan api key|"
    r"jawab dari pengetahuanmu|gunakan internet|gunakan web",
    re.I,
)
RECORD_ACCESS_PATTERN = re.compile(
    r"(cek|lihat|ambil|tampilkan).{0,30}(data penduduk|data warga|nik saya|status permohonan saya)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class PrivacyDecision:
    blocked: bool
    safe_message: str
    reason: str | None
    prompt_injection_signal: bool


def inspect_message(message: str) -> PrivacyDecision:
    prompt_signal = bool(PROMPT_INJECTION_PATTERN.search(message))
    if NATIONAL_ID_PATTERN.search(message):
        return PrivacyDecision(True, "[DATA SENSITIF DIBLOKIR]", "national_id", prompt_signal)
    if CREDENTIAL_PATTERN.search(message):
        return PrivacyDecision(True, "[DATA SENSITIF DIBLOKIR]", "credential", prompt_signal)
    if RECORD_ACCESS_PATTERN.search(message):
        return PrivacyDecision(
            True, "[PERMINTAAN AKSES DATA DIBLOKIR]", "record_access", prompt_signal
        )
    return PrivacyDecision(False, message, None, prompt_signal)
