"""Spec §7 — credentials are ciphertext at rest and never leave over HTTP."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.core import crypto

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_A])
def test_round_trip():
    ciphertext = crypto.encrypt("super-secret-api-key")
    assert ciphertext != "super-secret-api-key"
    assert crypto.decrypt(ciphertext) == "super-secret-api-key"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_A])
def test_ciphertext_does_not_contain_the_plaintext():
    assert "super-secret" not in crypto.encrypt("super-secret-api-key")


def test_missing_key_is_a_configuration_error_not_a_silent_plaintext_write():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[]):
        with pytest.raises(ImproperlyConfigured):
            crypto.encrypt("anything")


def test_rotation_keeps_old_ciphertext_readable():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_A]):
        old = crypto.encrypt("key-from-before-rotation")
    # New key first, old key retained for decryption.
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_B, KEY_A]):
        assert crypto.decrypt(old) == "key-from-before-rotation"
        fresh = crypto.encrypt("key-after-rotation")
    # Once the old key is dropped, old ciphertext is unreadable — by design.
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_B]):
        assert crypto.decrypt(fresh) == "key-after-rotation"
        with pytest.raises(crypto.CredentialDecryptionError):
            crypto.decrypt(old)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_A])
def test_fingerprint_is_stable_and_not_reversible():
    assert crypto.fingerprint("abc") == crypto.fingerprint("abc")
    assert crypto.fingerprint("abc") != crypto.fingerprint("abd")
    assert "abc" not in crypto.fingerprint("abc")
    assert len(crypto.fingerprint("abc")) == 8


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY_A])
@pytest.mark.django_db
def test_account_serializer_never_exposes_credentials():
    from apps.accounts.models import ConnectedAccount, Exchange
    from apps.accounts.serializers import ConnectedAccountSerializer

    account = ConnectedAccount(label="partner-1", exchange=Exchange.BYBIT)
    account.set_credentials(api_key="live-key", api_secret="live-secret")
    account.save()

    payload = ConnectedAccountSerializer(account).data
    serialized = str(payload)
    assert "live-key" not in serialized
    assert "live-secret" not in serialized
    assert not any("encrypted" in field for field in payload)
