import secrets

from app.core.security import digest_token, secure_compare_digest


def generate_csrf_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, digest_token(raw)


def validate_csrf(raw: str | None, expected_digest: str) -> bool:
    return bool(raw) and secure_compare_digest(raw, expected_digest)
