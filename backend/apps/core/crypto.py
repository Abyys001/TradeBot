"""Credential encryption at rest (spec §7).

API keys and Hyperliquid agent private keys are stored as Fernet ciphertext.
Keys come from ``CREDENTIAL_ENCRYPTION_KEYS`` — the first entry encrypts, all
entries can decrypt, which makes rotation a config change plus a re-save.

Rules for anyone touching this module:
  - never log plaintext, never put it in a serializer, never return it over HTTP
  - decrypt only inside an adapter, at the moment of signing a request
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class CredentialDecryptionError(Exception):
    """Ciphertext could not be decrypted with any configured key."""


def _fernet() -> MultiFernet:
    keys = settings.CREDENTIAL_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured(
            "CREDENTIAL_ENCRYPTION_KEYS is empty. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "CREDENTIAL_ENCRYPTION_KEYS contains a malformed Fernet key"
        ) from exc


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "Stored credential could not be decrypted. The encryption key was "
            "probably rotated without re-saving this account."
        ) from exc


def fingerprint(plaintext: str) -> str:
    """Short, non-reversible label so the UI can identify a key without showing it."""
    import hashlib

    if not plaintext:
        return ""
    return hashlib.sha256(plaintext.encode()).hexdigest()[:8]
