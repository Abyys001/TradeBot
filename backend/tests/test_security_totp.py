"""`docs/security-plan.md` §2 A1 — enrolment, and why it takes three steps.

`test_security_login.py` covers what a code does at sign-in. This file covers
the part before that: getting a device enrolled at all, and the refusals that
stand between an operator and a prompt they cannot answer.

The three steps exist because a secret written but never proved would arm a
prompt nobody can answer, and recovery codes minted but never saved would leave
a lost phone as a lost platform. `flags.set_flags` will not arm the switch
until all three are done, which is the lock-out escape stated as a refusal.
"""

from __future__ import annotations

import pyotp
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.security import flags, totp
from apps.security.models import SecurityPolicy, TotpDevice, TrustedDevice

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()
PASSWORD = "pw12345!"

BEGIN = "/api/security/totp/begin/"
CONFIRM = "/api/security/totp/confirm/"
ACKNOWLEDGE = "/api/security/totp/acknowledge/"
DISABLE = "/api/security/totp/disable/"
TOTP = "/api/security/totp/"
SECURITY_POLICY = "/api/security/policy/"


@pytest.fixture(autouse=True)
def _encryption_key():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def staff_client(username: str = "boss") -> tuple[Client, User]:
    user = User.objects.create_user(username, password=PASSWORD, is_staff=True)
    client = Client()
    assert client.login(username=username, password=PASSWORD)
    return client, user


def post(client: Client, url: str, body: dict | None = None):
    return client.post(url, body or {}, content_type="application/json")


# --------------------------------------------------------------------------
# The three steps
# --------------------------------------------------------------------------


def test_beginning_enrolment_arms_nothing():
    client, user = staff_client()

    started = post(client, BEGIN).json()

    assert started["secret"]
    assert started["uri"].startswith("otpauth://totp/")
    assert "TradeBot" in started["uri"]
    assert started["qr_svg"].startswith("<?xml") or "<svg" in started["qr_svg"]
    assert totp.device_state(user) == {
        "enrolled": True, "confirmed": False, "ready": False,
        "recovery_remaining": 0, "trusted_devices": 0,
    }
    assert totp.required_for(user) is False


def test_the_secret_is_encrypted_at_rest_like_every_other_credential():
    client, user = staff_client()

    secret = post(client, BEGIN).json()["secret"]

    stored = TotpDevice.objects.get(user=user).secret
    assert secret not in stored
    assert stored != secret


def test_a_wrong_code_does_not_confirm_the_enrolment():
    client, user = staff_client()
    post(client, BEGIN)

    refused = post(client, CONFIRM, {"code": "000000"})

    assert refused.status_code == 400
    assert "check the time" in refused.json()["detail"]
    assert TotpDevice.objects.get(user=user).confirmed_at is None


def test_confirming_mints_the_recovery_codes_once():
    client, user = staff_client()
    secret = post(client, BEGIN).json()["secret"]

    confirmed = post(client, CONFIRM, {"code": pyotp.TOTP(secret).now()}).json()

    assert len(confirmed["recovery_codes"]) == totp.RECOVERY_CODES
    assert confirmed["confirmed"] is True
    # Confirmed, but not yet *ready* — the codes have not been acknowledged.
    assert confirmed["ready"] is False

    device = TotpDevice.objects.get(user=user)
    for code in confirmed["recovery_codes"]:
        assert code not in str(device.recovery_codes)


def test_acknowledging_the_codes_is_what_makes_the_device_ready():
    client, user = staff_client()
    secret = post(client, BEGIN).json()["secret"]
    post(client, CONFIRM, {"code": pyotp.TOTP(secret).now()})

    assert totp.required_for(user) is False

    acknowledged = post(client, ACKNOWLEDGE).json()

    assert acknowledged["ready"] is True
    assert totp.required_for(user) is True


def test_restarting_enrolment_throws_the_half_finished_one_away():
    """An operator who lost the phone mid-enrolment should not need unpicking."""
    client, user = staff_client()
    first = post(client, BEGIN).json()["secret"]
    post(client, CONFIRM, {"code": pyotp.TOTP(first).now()})

    second = post(client, BEGIN).json()["secret"]

    assert second != first
    device = TotpDevice.objects.get(user=user)
    assert device.confirmed_at is None
    assert device.recovery_codes == []


# --------------------------------------------------------------------------
# The gate in front of the switch
# --------------------------------------------------------------------------


def test_the_switch_will_not_arm_before_the_enrolment_is_finished():
    client, _ = staff_client()

    refused = post(client, SECURITY_POLICY, {"two_factor": True})
    assert refused.status_code == 400
    assert refused.json()["code"] == "policy_refused"

    secret = post(client, BEGIN).json()["secret"]
    assert post(client, SECURITY_POLICY, {"two_factor": True}).status_code == 400

    post(client, CONFIRM, {"code": pyotp.TOTP(secret).now()})
    assert post(client, SECURITY_POLICY, {"two_factor": True}).status_code == 400

    post(client, ACKNOWLEDGE)
    assert post(client, SECURITY_POLICY, {"two_factor": True}).status_code == 200
    assert flags.is_on("two_factor") is True


# --------------------------------------------------------------------------
# Taking it off again
# --------------------------------------------------------------------------


def test_removing_the_second_factor_needs_the_password():
    client, user = staff_client()
    secret = post(client, BEGIN).json()["secret"]
    post(client, CONFIRM, {"code": pyotp.TOTP(secret).now()})
    post(client, ACKNOWLEDGE)

    assert post(client, DISABLE, {"password": "wrong"}).status_code == 401
    assert TotpDevice.objects.filter(user=user).exists()

    assert post(client, DISABLE, {"password": PASSWORD}).status_code == 200
    assert TotpDevice.objects.filter(user=user).exists() is False


def test_removing_the_device_disarms_the_switch_rather_than_stranding_it():
    """Leaving `two_factor` on with nobody enrolled would demand a code at the
    next sign-in that nobody can produce."""
    client, _ = staff_client()
    secret = post(client, BEGIN).json()["secret"]
    post(client, CONFIRM, {"code": pyotp.TOTP(secret).now()})
    post(client, ACKNOWLEDGE)
    post(client, SECURITY_POLICY, {"two_factor": True})
    assert flags.is_on("two_factor") is True

    post(client, DISABLE, {"password": PASSWORD})

    assert flags.is_on("two_factor") is False
    assert SecurityPolicy.objects.get(pk=1).two_factor is False


def test_removing_the_device_forgets_every_remembered_browser_with_it():
    client, user = staff_client()
    secret = post(client, BEGIN).json()["secret"]
    post(client, CONFIRM, {"code": pyotp.TOTP(secret).now()})
    post(client, ACKNOWLEDGE)
    TrustedDevice.objects.create(
        user=user, token_hash=TrustedDevice.hash_token("t"),
        expires_at=TotpDevice.objects.get(user=user).created_at,
    )

    post(client, DISABLE, {"password": PASSWORD})

    assert TrustedDevice.objects.count() == 0


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------


def test_none_of_it_is_reachable_without_a_staff_session():
    User.objects.create_user("intern", password=PASSWORD, is_staff=False)
    client = Client()
    client.login(username="intern", password=PASSWORD)

    for url in (TOTP, BEGIN, CONFIRM, ACKNOWLEDGE, DISABLE):
        assert client.get(url).status_code in (401, 403, 405)
        assert post(client, url).status_code in (401, 403)
