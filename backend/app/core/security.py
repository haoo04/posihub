"""Symmetric encryption utilities for protecting API credentials at rest.

Uses Fernet (AES128-CBC + HMAC-SHA256) from `cryptography`. The encryption key
is loaded from the `POSIHUB_ENCRYPTION_KEY` environment variable. Plaintext
values are never logged.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class EncryptionKeyMissing(RuntimeError):
    """Raised when no encryption key has been configured."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.posihub_encryption_key
    if not key:
        raise EncryptionKeyMissing(
            "POSIHUB_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"`."
        )
    return Fernet(key.encode("utf-8"))


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt a secret. Returns ``None`` if input is empty."""

    if plaintext is None or plaintext == "":
        return None
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(token: str | None) -> str | None:
    """Decrypt a previously-encrypted secret. Returns ``None`` if input is empty."""

    if token is None or token == "":
        return None
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt secret: invalid token or wrong key") from exc


def mask_secret(plaintext: str | None, visible: int = 4) -> str:
    """Return a masked representation of a secret for safe display/logging."""

    if not plaintext:
        return ""
    if len(plaintext) <= visible:
        return "*" * len(plaintext)
    return f"{plaintext[:visible]}{'*' * (len(plaintext) - visible)}"


def generate_key() -> str:
    """Generate a new Fernet key (utility for first-time setup)."""

    return Fernet.generate_key().decode("utf-8")
