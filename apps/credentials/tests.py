"""Phase 1 verification tests for credential encryption."""
import pytest
from django.contrib.auth import get_user_model

from .crypto import decrypt, encrypt
from .models import Exchange, ExchangeCredential, Network


def test_encrypt_decrypt_round_trip():
    secret = "abcd1234" * 8  # 64 hex chars
    token = encrypt(secret)
    assert isinstance(token, bytes)
    assert token != secret.encode()
    assert decrypt(token) == secret


def test_encrypt_uses_fresh_nonce_each_call():
    a = encrypt("same")
    b = encrypt("same")
    assert a != b
    assert decrypt(a) == decrypt(b) == "same"


def test_decrypt_rejects_tampered_ciphertext():
    token = bytearray(encrypt("tamper-me"))
    token[-1] ^= 0xFF
    with pytest.raises(Exception):
        decrypt(bytes(token))


@pytest.mark.django_db
def test_agent_key_stored_encrypted_at_rest():
    User = get_user_model()
    user = User.objects.create_user(username="alice", password="pw")
    agent_key = "0x" + "ab" * 32

    cred = ExchangeCredential(
        user=user,
        label="main",
        exchange=Exchange.HYPERLIQUID,
        wallet_address="0x" + "cd" * 20,
        network=Network.TESTNET,
    )
    cred.set_agent_key(agent_key)
    cred.save()

    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT agent_private_key_enc FROM credentials_exchangecredential WHERE id = %s",
            [cred.id],
        )
        row = cur.fetchone()

    raw_blob = bytes(row[0])
    assert b"abababab" not in raw_blob

    cred.refresh_from_db()
    assert cred.get_agent_key().lower() == agent_key.lower()
