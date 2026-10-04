import pytest

from app.core.security import (
    DUMMY_HASH,
    digest_token,
    hash_password,
    normalize_username,
    secure_compare_digest,
    validate_new_password,
    validate_username,
    verify_password,
)


def test_username_normalized() -> None:
    assert normalize_username("  Admin.User  ") == "admin.user"


@pytest.mark.parametrize("value", ["ab", "has space", "_starts", "a" * 65])
def test_invalid_username_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        validate_username(value)


def test_valid_username_accepted() -> None:
    assert validate_username("administrator") == "administrator"


def test_argon2_hash_and_verify() -> None:
    encoded = hash_password("Correct Horse Battery 123")
    valid, _ = verify_password("Correct Horse Battery 123", encoded)
    assert encoded.startswith("$argon2id$")
    assert encoded != "Correct Horse Battery 123"
    assert valid is True


def test_wrong_password_fails() -> None:
    encoded = hash_password("Correct Horse Battery 123")
    assert verify_password("wrong", encoded)[0] is False


def test_dummy_hash_uses_same_path() -> None:
    assert verify_password("wrong", DUMMY_HASH)[0] is False


@pytest.mark.parametrize(
    "password",
    ["short", "administrator", "password1234", "bad\npassword123"],
)
def test_new_password_policy_rejects(password: str) -> None:
    with pytest.raises(ValueError):
        validate_new_password(password, "administrator", password)


def test_password_is_not_trimmed() -> None:
    validate_new_password("  long passphrase value  ", "administrator", "  long passphrase value  ")


def test_confirmation_mismatch() -> None:
    with pytest.raises(ValueError):
        validate_new_password("Correct Horse Battery 123", "administrator", "different value")


def test_token_digest_and_constant_compare() -> None:
    raw = "token-secret"
    digest = digest_token(raw)
    assert len(digest) == 64
    assert raw not in digest
    assert secure_compare_digest(raw, digest)
    assert not secure_compare_digest("wrong", digest)
