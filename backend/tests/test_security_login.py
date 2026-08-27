"""`docs/security-plan.md` §2 A1–A5 — the sign-in path, switch by switch.

The load-bearing test in this file is the first one: with every control off the
sequence is authenticate → staff check → `login()` → record the session, which
is what it was before this layer existed. Everything after it turns exactly one
switch on and checks that it did exactly one thing.
"""

from __future__ import annotations

import time

import pyotp
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.accounts.models import Notification, PanelSession
from apps.security import flags, totp
from apps.security.models import (
    SecurityEvent,
    SecurityEventKind,
    SecurityPolicy,
    TotpDevice,
    TrustedDevice,
)

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()

LOGIN = "/api/accounts/auth/login/"
MFA = "/api/accounts/auth/mfa/"
LOGOUT = "/api/accounts/auth/logout/"
ME = "/api/accounts/auth/me/"
SESSIONS = "/api/accounts/auth/sessions/"

PASSWORD = "pw12345!"


@pytest.fixture(autouse=True)
def _encryption_key():
    """The TOTP secret goes through the same vault the API keys do."""
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def boss(username: str = "boss", *, staff: bool = True) -> User:
    return User.objects.create_user(username, password=PASSWORD, is_staff=staff)


def arm(**switches) -> None:
    SecurityPolicy.objects.update_or_create(pk=1, defaults=switches)
    flags.invalidate()


def sign_in(client: Client, username: str = "boss", password: str = PASSWORD, **extra):
    return client.post(
        LOGIN, {"username": username, "password": password, **extra},
        content_type="application/json",
    )


def enrol(user) -> tuple[str, list[str]]:
    """Take a user all the way through the three enrolment steps.

    `last_step` is wound back afterwards because confirming the enrolment
    *spends* the current 30-second step — the replay guard is doing its job.
    A real operator's next sign-in is minutes later; a test's is microseconds,
    and rewinding here is what lets the guard still be tested on its own in
    `test_the_same_code_cannot_be_used_twice`.
    """
    started = totp.begin(user)
    secret = started["secret"]
    codes = totp.confirm(user, pyotp.TOTP(secret).now())
    totp.acknowledge_recovery(user)
    TotpDevice.objects.filter(user=user).update(last_step=0)
    return secret, codes


def code_for(secret: str, *, at: float | None = None) -> str:
    return pyotp.TOTP(secret).at(int(at if at is not None else time.time()))


# --------------------------------------------------------------------------
# Off is the sign-in that was already there
# --------------------------------------------------------------------------


def test_with_everything_off_a_sign_in_is_what_it_always_was():
    boss()
    client = Client()

    response = sign_in(client)

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert client.get(ME).json()["authenticated"] is True
    assert PanelSession.objects.filter(username="boss", ended_at=None).count() == 1
    # Nothing was logged, no code was asked for, no device was remembered.
    assert SecurityEvent.objects.count() == 0
    assert Notification.objects.count() == 0
    assert TrustedDevice.objects.count() == 0


def test_a_wrong_password_is_still_a_plain_401_with_nothing_counted():
    boss()

    response = sign_in(Client(), password="wrong")

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid username or password"
    assert SecurityEvent.objects.count() == 0


def test_a_non_staff_user_is_refused_whatever_the_switches_say():
    boss("intern", staff=False)

    assert sign_in(Client(), "intern").status_code == 403


# --------------------------------------------------------------------------
# A2 — the sign-in limiter
# --------------------------------------------------------------------------


def test_the_limiter_is_inert_until_it_is_switched_on():
    boss()
    client = Client()

    for _ in range(10):
        assert sign_in(client, password="wrong").status_code == 401

    assert sign_in(client).status_code == 200


def test_a_run_of_wrong_passwords_becomes_a_wait():
    boss()
    arm(login_rate_limit=True, login_max_attempts=3, login_lockout_seconds=900)
    client = Client()

    codes = [sign_in(client, password="wrong").status_code for _ in range(3)]
    assert codes == [401, 401, 401]

    locked = sign_in(client, password="wrong")
    assert locked.status_code == 429
    assert locked.json()["code"] == "rate_limited"
    assert 0 < locked.json()["retry_after"] <= 900

    # And the right password does not get past it either — otherwise the
    # limiter would only be slowing down the attacker who is already wrong.
    assert sign_in(client).status_code == 429


def test_a_successful_sign_in_forgets_the_failures_before_it():
    boss()
    arm(login_rate_limit=True, login_max_attempts=3)
    client = Client()

    sign_in(client, password="wrong")
    sign_in(client, password="wrong")
    assert sign_in(client).status_code == 200

    client.post(LOGOUT, content_type="application/json")
    assert sign_in(client, password="wrong").status_code == 401


# --------------------------------------------------------------------------
# A1/A3 — the second factor and the trusted browser
# --------------------------------------------------------------------------


def test_a_code_is_asked_for_only_once_the_switch_and_the_enrolment_agree():
    user = boss()
    arm(two_factor=True)
    client = Client()

    # Switch on, nobody enrolled: let through rather than stranded.
    assert sign_in(client).status_code == 200
    client.post(LOGOUT, content_type="application/json")

    enrol(user)
    challenged = sign_in(client)
    assert challenged.status_code == 200
    assert challenged.json()["mfa_required"] is True
    assert challenged.json()["challenge"]
    assert client.get(ME).json()["authenticated"] is False


def test_the_challenge_completes_with_a_code_from_the_app():
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True)
    client = Client()

    challenge = sign_in(client).json()["challenge"]
    done = client.post(
        MFA, {"challenge": challenge, "code": code_for(secret)},
        content_type="application/json",
    )

    assert done.status_code == 200
    assert done.json()["authenticated"] is True
    assert SecurityEvent.objects.filter(kind=SecurityEventKind.MFA_OK).exists() is False


def test_the_same_code_cannot_be_used_twice():
    """A code is valid for a whole step, so a shoulder-surfed one would
    otherwise work again inside the minute."""
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True)
    code = code_for(secret)

    first = Client()
    challenge = sign_in(first).json()["challenge"]
    assert first.post(
        MFA, {"challenge": challenge, "code": code}, content_type="application/json"
    ).status_code == 200

    second = Client()
    challenge = sign_in(second).json()["challenge"]
    replayed = second.post(
        MFA, {"challenge": challenge, "code": code}, content_type="application/json"
    )
    assert replayed.status_code == 401


def test_a_recovery_code_gets_in_once_and_then_never_again():
    user = boss()
    _, codes = enrol(user)
    arm(two_factor=True)

    first = Client()
    challenge = sign_in(first).json()["challenge"]
    assert first.post(
        MFA, {"challenge": challenge, "code": codes[0]}, content_type="application/json"
    ).status_code == 200

    assert TotpDevice.objects.get(user=user).recovery_remaining == len(codes) - 1

    second = Client()
    challenge = sign_in(second).json()["challenge"]
    assert second.post(
        MFA, {"challenge": challenge, "code": codes[0]}, content_type="application/json"
    ).status_code == 401


def test_an_expired_or_invented_challenge_is_refused():
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True)
    client = Client()

    response = client.post(
        MFA, {"challenge": "not-a-real-token", "code": code_for(secret)},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "challenge_expired"


def test_a_remembered_browser_skips_the_code_and_an_unknown_one_does_not():
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True, trusted_devices=True, trusted_device_days=30)

    client = Client()
    challenge = sign_in(client, remember=True).json()["challenge"]
    client.post(
        MFA, {"challenge": challenge, "code": code_for(secret), "remember": True},
        content_type="application/json",
    )
    assert TrustedDevice.objects.filter(user=user).count() == 1
    assert totp.TRUST_COOKIE in client.cookies

    client.post(LOGOUT, content_type="application/json")
    again = sign_in(client)
    assert again.json().get("mfa_required") is None
    assert again.json()["authenticated"] is True

    assert sign_in(Client()).json()["mfa_required"] is True


def test_forgetting_the_remembered_browsers_brings_the_code_back():
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True, trusted_devices=True, trusted_device_days=30)

    client = Client()
    challenge = sign_in(client, remember=True).json()["challenge"]
    client.post(
        MFA, {"challenge": challenge, "code": code_for(secret), "remember": True},
        content_type="application/json",
    )

    forgotten = client.post("/api/security/trusted/forget/", content_type="application/json")
    assert forgotten.status_code == 200
    assert forgotten.json()["forgotten"] == 1

    client.post(LOGOUT, content_type="application/json")
    assert sign_in(client).json()["mfa_required"] is True


def test_the_trust_cookie_is_httponly_and_scoped_to_the_panel():
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True, trusted_devices=True, trusted_device_days=30)

    client = Client()
    challenge = sign_in(client, remember=True).json()["challenge"]
    client.post(
        MFA, {"challenge": challenge, "code": code_for(secret), "remember": True},
        content_type="application/json",
    )

    cookie = client.cookies[totp.TRUST_COOKIE]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/"
    # The stored row is a hash, never the token itself — the session rule.
    assert TrustedDevice.objects.get(user=user).token_hash != cookie.value


def test_a_browser_is_not_remembered_unless_both_switches_are_on():
    user = boss()
    secret, _ = enrol(user)
    arm(two_factor=True, trusted_devices=False)

    client = Client()
    challenge = sign_in(client, remember=True).json()["challenge"]
    client.post(
        MFA, {"challenge": challenge, "code": code_for(secret), "remember": True},
        content_type="application/json",
    )

    assert TrustedDevice.objects.count() == 0


# --------------------------------------------------------------------------
# A4 — the new-device notice
# --------------------------------------------------------------------------


def test_a_new_browser_raises_a_persistent_notice_only_when_asked_to():
    boss()
    arm(new_device_notice=True)

    sign_in(Client(), HTTP_USER_AGENT="Mozilla/5.0 (Macintosh) Safari/605")

    notice = Notification.objects.get()
    assert notice.code == "new_device"
    assert notice.account_id is None
    assert "boss" in notice.message


def test_a_browser_that_has_signed_in_before_raises_nothing():
    boss()
    arm(new_device_notice=True)
    agent = "Mozilla/5.0 (X11; Linux x86_64) Firefox/128"

    sign_in(Client(), HTTP_USER_AGENT=agent)
    Notification.objects.all().delete()

    sign_in(Client(), HTTP_USER_AGENT=agent)

    assert Notification.objects.count() == 0


# --------------------------------------------------------------------------
# A5 — one browser at a time
# --------------------------------------------------------------------------


def test_single_session_ends_the_other_browsers_and_leaves_this_one():
    boss()
    first = Client()
    sign_in(first)
    assert first.get(ME).json()["authenticated"] is True

    arm(single_session=True)
    second = Client()
    sign_in(second)

    assert second.get(ME).json()["authenticated"] is True
    assert first.get(ME).json()["authenticated"] is False
    assert PanelSession.objects.filter(ended_at=None).count() == 1


def test_without_the_switch_both_browsers_stay_signed_in():
    boss()
    first, second = Client(), Client()
    sign_in(first)
    sign_in(second)

    assert first.get(ME).json()["authenticated"] is True
    assert second.get(ME).json()["authenticated"] is True


# --------------------------------------------------------------------------
# Revoking a session — not a switch, and never optional
# --------------------------------------------------------------------------


def test_one_browser_can_end_another_but_not_itself():
    boss()
    other = Client()
    sign_in(other)
    here = Client()
    sign_in(here)

    rows = here.get(SESSIONS).json()["sessions"]
    theirs = next(row for row in rows if not row["current"])
    mine = next(row for row in rows if row["current"])

    refused = here.post(f"/api/accounts/auth/sessions/{mine['id']}/revoke/",
                        content_type="application/json")
    assert refused.status_code == 400
    assert refused.json()["code"] == "own_session"

    revoked = here.post(f"/api/accounts/auth/sessions/{theirs['id']}/revoke/",
                        content_type="application/json")
    assert revoked.status_code == 200
    assert other.get(ME).json()["authenticated"] is False
    assert here.get(ME).json()["authenticated"] is True
