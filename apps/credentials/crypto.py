"""AES-256-GCM encryption for exchange API secrets.

Layer 1 of multi-layer protection: authenticated encryption at the application
level. The master key (CREDENTIAL_ENC_KEY) is a base64-urlsafe-encoded 32-byte
key held only in the environment, never in the database.

On-disk format per encrypted field:  nonce(12) || ciphertext || tag(16)
(AESGCM.encrypt appends the 16-byte tag to the ciphertext automatically.)

Generate a key:
    python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

NONCE_SIZE = 12  # 96-bit nonce — recommended size for GCM.
KEY_SIZE = 32  # 256-bit key.


def _load_key() -> bytes:
    raw = getattr(settings, "CREDENTIAL_ENC_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured("CREDENTIAL_ENC_KEY is not set.")
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise ImproperlyConfigured("CREDENTIAL_ENC_KEY is not valid base64.") from exc
    if len(key) != KEY_SIZE:
        raise ImproperlyConfigured(
            f"CREDENTIAL_ENC_KEY must decode to {KEY_SIZE} bytes (got {len(key)})."
        )
    return key


def encrypt(plaintext: str) -> bytes:
    """Encrypt a UTF-8 string, returning nonce || ciphertext || tag."""
    if plaintext is None:
        raise ValueError("Cannot encrypt None.")
    aes = AESGCM(_load_key())
    nonce = os.urandom(NONCE_SIZE)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct


def decrypt(token: bytes) -> str:
    """Decrypt nonce || ciphertext || tag back to the original UTF-8 string."""
    if not token or len(token) <= NONCE_SIZE:
        raise ValueError("Ciphertext is missing or too short.")
    token = bytes(token)  # memoryview (from DB BinaryField) -> bytes
    aes = AESGCM(_load_key())
    nonce, ct = token[:NONCE_SIZE], token[NONCE_SIZE:]
    return aes.decrypt(nonce, ct, None).decode("utf-8")
