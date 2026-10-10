"""Tests for symmetric encryption helpers."""

from __future__ import annotations

from app.core.security import decrypt_secret, encrypt_secret, mask_secret


def test_encrypt_roundtrip() -> None:
    plaintext = "super-secret-api-key"
    token = encrypt_secret(plaintext)
    assert token is not None and token != plaintext
    assert decrypt_secret(token) == plaintext


def test_encrypt_handles_empty() -> None:
    assert encrypt_secret(None) is None
    assert encrypt_secret("") is None
    assert decrypt_secret(None) is None
    assert decrypt_secret("") is None


def test_mask_secret() -> None:
    assert mask_secret("abcdef12") == "abcd****"
    assert mask_secret("abc") == "***"
    assert mask_secret(None) == ""


def test_decrypt_credentials_from_cryptography_43() -> None:
    # Synthetic token generated with cryptography 43.0.3 and the test encryption key.
    token = "gAAAAABqyhR00SuEwiJUoEsgNH5d6ojU4gMV4rN5kMV7UsVrusGrRNJ3caKS648L8lEI7RAXVhyoeNTBViqO06xKiqLs2TvUEKtIOXrjXyHlEc-y4SoSZhE="
    assert decrypt_secret(token) == "synthetic legacy credential"
