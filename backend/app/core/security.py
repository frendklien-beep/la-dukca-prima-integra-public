import re
from hashlib import sha256
from hmac import compare_digest

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "$y1RStCWKSWtg3+M3RqImQ$moPxsQBhryY605Uw0GmuT2wlMLecBzv0M5iTo3hLybu"
)
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
DENYLIST = {"password1234", "administrator", "admin123456", "qwerty123456"}


def normalize_username(value: str) -> str:
    return value.strip().lower()


def validate_username(value: str) -> str:
    normalized = normalize_username(value)
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("Username tidak valid.")
    return normalized


def validate_new_password(password: str, username: str, confirmation: str | None = None) -> None:
    if confirmation is not None and password != confirmation:
        raise ValueError("Konfirmasi password tidak sama.")
    if not 12 <= len(password) <= 128:
        raise ValueError("Password harus 12 sampai 128 karakter.")
    if any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise ValueError("Password mengandung karakter kontrol.")
    if password.lower() == normalize_username(username) or password.lower() in DENYLIST:
        raise ValueError("Password terlalu mudah ditebak.")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> tuple[bool, str | None]:
    try:
        return password_hash.verify_and_update(password, encoded)
    except Exception:
        return False, None


def digest_token(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


def secure_compare_digest(raw: str, expected_digest: str) -> bool:
    return compare_digest(digest_token(raw), expected_digest)
