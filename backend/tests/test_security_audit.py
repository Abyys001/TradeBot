"""`docs/security-plan.md` §2 A7 — the access history, and what it never holds.

Two rules, and the file is mostly about the seams between them:

* **off means the work does not happen.** `audit.record` returns before it
  builds anything, so switching the log off is not "write it and hide it".
* **one write ignores that.** A change to the switches themselves is always
  recorded, because a log that can be switched off without leaving the fact
  behind is not a log.

The third group is the one that would matter after a breach: what a row is
allowed to contain. No password, no session key, no TOTP secret, no recovery
code, and no address list — checked against the actual rows the endpoints
write, not against the intent.
"""

from __future__ import annotations

import pyotp
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import Client, override_settings

from apps.security import audit, flags, totp
from apps.security.models import SecurityEvent, SecurityEventKind, SecurityPolicy

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()
PASSWORD = "pw12345!"

LOGIN = "/api/accounts/auth/login/"
LOGOUT = "/api/accounts/auth/logout/"
EVENTS = "/api/security/events/"
SECURITY_POLICY = "/api/security/policy/"


@pytest.fixture(autouse=True)
def _encryption_key():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def arm(**switches) -> None:
    SecurityPolicy.objects.update_or_create(pk=1, defaults=switches)
    flags.invalidate()


def staff_client(username: str = "boss") -> Client:
    User.objects.create_user(username, password=PASSWORD, is_staff=True)
    client = Client()
    assert client.login(username=username, password=PASSWORD)
    return client


def sign_in(client: Client, password: str = PASSWORD, **extra):
    return client.post(
        LOGIN, {"username": "boss", "password": password},
        content_type="application/json", **extra,
    )


# --------------------------------------------------------------------------
# Off means nothing is written
# --------------------------------------------------------------------------


def test_a_whole_session_with_the_log_off_leaves_no_rows():
    User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    client = Client()

    sign_in(client, password="wrong")
    sign_in(client)
    client.post(LOGOUT, content_type="application/json")

    assert SecurityEvent.objects.count() == 0


def test_record_returns_before_it_builds_anything(monkeypatch):
    """The contract stated as code: off is not "write it and discard it"."""
    monkeypatch.setattr(
        SecurityEvent.objects, "create",
        lambda **kwargs: pytest.fail("a row was built with the log off"),
    )

    audit.record(SecurityEventKind.LOGIN_OK, username="boss")


# --------------------------------------------------------------------------
# On means the sign-in path is recorded
# --------------------------------------------------------------------------


def test_the_sign_in_path_is_recorded_once_the_log_is_on():
    User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    arm(audit_log=True)
    client = Client()

    sign_in(client, password="wrong")
    sign_in(client)
    client.post(LOGOUT, content_type="application/json")

    kinds = list(SecurityEvent.objects.order_by("id").values_list("kind", flat=True))
    assert kinds == [
        SecurityEventKind.LOGIN_FAILED,
        SecurityEventKind.LOGIN_OK,
        SecurityEventKind.LOGOUT,
    ]


def test_a_row_carries_who_from_where_and_on_what():
    User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    arm(audit_log=True)

    sign_in(Client(), HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) Firefox/128")

    event = SecurityEvent.objects.get(kind=SecurityEventKind.LOGIN_OK)
    assert event.username == "boss"
    assert event.ip_address == "127.0.0.1"
    assert "Firefox" in event.user_agent


def test_a_refused_sign_in_records_the_username_that_was_tried():
    """Which is the whole point of the log — the attempts nobody made."""
    arm(audit_log=True)

    Client().post(
        LOGIN, {"username": "administrator", "password": "hunter2"},
        content_type="application/json",
    )

    event = SecurityEvent.objects.get()
    assert event.kind == SecurityEventKind.LOGIN_FAILED
    assert event.username == "administrator"


def test_the_second_factor_is_recorded_as_the_factor_it_used():
    user = User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    started = totp.begin(user)
    codes = totp.confirm(user, pyotp.TOTP(started["secret"]).now())
    totp.acknowledge_recovery(user)
    arm(two_factor=True, audit_log=True)

    client = Client()
    challenge = sign_in(client).json()["challenge"]
    client.post(
        "/api/accounts/auth/mfa/", {"challenge": challenge, "code": codes[0]},
        content_type="application/json",
    )

    assert SecurityEvent.objects.filter(kind=SecurityEventKind.RECOVERY_USED).exists()


# --------------------------------------------------------------------------
# The one write that ignores the switch
# --------------------------------------------------------------------------


def test_a_change_to_the_switches_is_recorded_even_with_the_log_off():
    client = staff_client()

    response = client.post(
        SECURITY_POLICY, {"login_rate_limit": True}, content_type="application/json"
    )
    assert response.status_code == 200

    event = SecurityEvent.objects.get(kind=SecurityEventKind.POLICY_CHANGED)
    assert event.username == "boss"
    assert event.detail["changed"] == {"login_rate_limit": ["False", "True"]}


def test_switching_the_log_itself_off_is_the_last_thing_it_records():
    client = staff_client()
    arm(audit_log=True)

    client.post(SECURITY_POLICY, {"audit_log": False}, content_type="application/json")

    assert SecurityEvent.objects.filter(kind=SecurityEventKind.POLICY_CHANGED).count() == 1
    assert flags.is_on("audit_log") is False


def test_a_save_that_changes_nothing_records_nothing():
    client = staff_client()

    client.post(SECURITY_POLICY, {"audit_log": False}, content_type="application/json")

    assert SecurityEvent.objects.count() == 0


# --------------------------------------------------------------------------
# What a row may never contain
# --------------------------------------------------------------------------


def test_no_row_ever_carries_a_secret():
    user = User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    started = totp.begin(user)
    secret = started["secret"]
    codes = totp.confirm(user, pyotp.TOTP(secret).now())
    totp.acknowledge_recovery(user)
    arm(two_factor=True, audit_log=True, ip_allowlist=True, allowed_ips="127.0.0.1")

    client = Client()
    sign_in(client, password="wrong")
    challenge = sign_in(client).json()["challenge"]
    client.post(
        "/api/accounts/auth/mfa/", {"challenge": challenge, "code": codes[0]},
        content_type="application/json",
    )
    client.post(SECURITY_POLICY, {"login_rate_limit": True},
                content_type="application/json")

    forbidden = [PASSWORD, secret, challenge, codes[0], "10.0.0.1", "127.0.0.1"]
    for event in SecurityEvent.objects.all():
        blob = str(event.detail)
        for needle in forbidden:
            assert needle not in blob, f"{event.kind} carries {needle[:6]}…"


def test_the_allowlist_contents_stay_out_of_the_history():
    """An address list in a history is a map somebody may page through
    casually; it belongs on the settings row and nowhere else."""
    client = staff_client()

    client.post(
        SECURITY_POLICY, {"ip_allowlist": True, "allowed_ips": "203.0.113.7"},
        content_type="application/json",
    )

    event = SecurityEvent.objects.get(kind=SecurityEventKind.POLICY_CHANGED)
    assert "203.0.113.7" not in str(event.detail)
    # The name stays — that the list moved is exactly what a history is for.
    assert event.detail["changed"]["allowed_ips"] == ["(changed)", "(changed)"]


# --------------------------------------------------------------------------
# Reading it back, and surviving it
# --------------------------------------------------------------------------


def test_the_history_reads_back_newest_first_with_a_readable_label():
    client = staff_client()
    arm(audit_log=True)
    client.post(LOGOUT, content_type="application/json")
    sign_in(client)

    events = client.get(EVENTS).json()["events"]

    assert [row["kind"] for row in events][:2] == [
        SecurityEventKind.LOGIN_OK,
        SecurityEventKind.LOGOUT,
    ]
    assert events[0]["label"] == "Signed in"


def test_the_history_is_staff_only():
    User.objects.create_user("intern", password=PASSWORD, is_staff=False)
    client = Client()
    client.login(username="intern", password=PASSWORD)

    assert client.get(EVENTS).status_code in (401, 403)


def test_a_history_that_cannot_be_written_does_not_take_the_request_with_it(monkeypatch):
    """The log is a record of the platform, not a dependency of it."""
    User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    arm(audit_log=True)

    def explode(**kwargs):
        raise DatabaseError("no room")

    monkeypatch.setattr(SecurityEvent.objects, "create", explode)

    assert sign_in(Client()).status_code == 200
