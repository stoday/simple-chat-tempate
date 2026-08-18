import pytest


def test_password_hashing_works_with_installed_bcrypt_backend():
    from backend.main import hash_password, verify_password

    password_hash = hash_password("password123")

    assert password_hash.startswith("$2")
    assert verify_password("password123", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_password_hashing_rejects_values_over_bcrypt_byte_limit():
    from backend.main import hash_password

    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("密" * 73)
