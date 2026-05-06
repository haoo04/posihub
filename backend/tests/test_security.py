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
