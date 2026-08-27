"""`docs/security-plan.md` §2 B1–B3 — the three controls that see every request.

`test_security_cost.py` covers what these cost. This file covers what they do:
who they refuse, who they must never refuse, and the fact that each one is
inert until its own switch is on.
"""

from __future__ import annotations

import time

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.security import flags
from apps.security.middleware import LOGIN_AT_KEY
from apps.security.models import CspMode, SecurityEvent, SecurityEventKind, SecurityPolicy

pytestmark = pytest.mark.django_db

PASSWORD = "pw12345!"
POLICY = "/api/trading/policy/"
STOP_ALL = "/api/trading/stop-all/"
HEALTH = "/api/health/"
CSP = "/api/security/csp/"
ME = "/api/accounts/auth/me/"
SECURITY_POLICY = "/api/security/policy/"


def arm(**switches) -> None:
    SecurityPolicy.objects.update_or_create(pk=1, defaults=switches)
    flags.invalidate()


def staff_client(username: str = "boss") -> Client:
    User.objects.create_user(username, password=PASSWORD, is_staff=True)
    client = Client()
    assert client.login(username=username, password=PASSWORD)
    return client


# --------------------------------------------------------------------------
# B1 — the address allowlist
# --------------------------------------------------------------------------


def test_the_allowlist_is_inert_until_it_is_switched_on():
    client = staff_client()
    arm(ip_allowlist=False, allowed_ips="10.0.0.1")

    assert client.get(POLICY).status_code == 200


def test_an_address_on_the_list_gets_through_and_one_off_it_does_not():
    client = staff_client()

    arm(ip_allowlist=True, allowed_ips="127.0.0.1")
    assert client.get(POLICY).status_code == 200

    arm(ip_allowlist=True, allowed_ips="10.0.0.1")
    refused = client.get(POLICY)
    assert refused.status_code == 403
    assert refused.json()["code"] == "ip_not_allowed"


def test_a_cidr_block_covers_the_addresses_inside_it():
    client = staff_client()
    arm(ip_allowlist=True, allowed_ips="127.0.0.0/24")

    assert client.get(POLICY).status_code == 200


def test_a_typo_in_the_list_drops_that_entry_rather_than_breaking_the_panel():
    """A saved typo is read on every request; it must not be able to 500."""
    client = staff_client()
    arm(ip_allowlist=True, allowed_ips="not-an-address\n127.0.0.1")

    assert client.get(POLICY).status_code == 200

    arm(ip_allowlist=True, allowed_ips="not-an-address")
    assert client.get(POLICY).status_code == 403


def test_the_halt_and_the_health_check_stay_reachable_from_anywhere():
    """The lock-out escape: a blocked operator can still stop the platform."""
    client = staff_client()
    arm(ip_allowlist=True, allowed_ips="10.0.0.1")

    assert client.get(POLICY).status_code == 403
    assert client.get(STOP_ALL).status_code == 200
    assert client.get(HEALTH).status_code == 200
    assert client.get(CSP).status_code == 200


def test_a_blocked_request_is_recorded_when_the_log_is_on():
    client = staff_client()
    arm(ip_allowlist=True, allowed_ips="10.0.0.1", audit_log=True)

    client.get(POLICY)

    event = SecurityEvent.objects.get(kind=SecurityEventKind.IP_BLOCKED)
    assert event.detail["path"] == POLICY


# --------------------------------------------------------------------------
# B2 — the idle and absolute session windows
# --------------------------------------------------------------------------


def test_the_idle_window_is_inert_until_it_is_switched_on():
    client = staff_client()
    arm(idle_timeout=False, idle_timeout_minutes=1)

    session = client.session
    assert client.get(ME).json()["authenticated"] is True
    # Nothing rewrote the session's deadline.
    assert client.session.get_expiry_age() == session.get_expiry_age()


def test_the_idle_window_moves_forward_on_every_request():
    client = staff_client()
    arm(idle_timeout=True, idle_timeout_minutes=30)

    assert client.get(ME).json()["authenticated"] is True
    assert client.session.get_expiry_age() <= 30 * 60


def test_a_session_past_its_absolute_age_is_signed_out():
    client = staff_client()
    arm(idle_timeout=True, session_max_hours=1)

    session = client.session
    session[LOGIN_AT_KEY] = time.time() - 7200
    session.save()

    expired = client.get(POLICY)
    assert expired.status_code == 401
    assert expired.json()["code"] == "session_expired"
    assert client.get(ME).json()["authenticated"] is False


def test_a_signed_out_visitor_is_not_measured_against_a_session_window():
    """The window applies to a sign-in, and an anonymous caller has none."""
    arm(idle_timeout=True, session_max_hours=1)

    assert Client().get(ME).json()["authenticated"] is False


# --------------------------------------------------------------------------
# B3 — the admin-write limiter
# --------------------------------------------------------------------------


def test_the_write_limiter_is_inert_until_it_is_switched_on():
    client = staff_client()
    arm(admin_write_rate_limit=False, admin_write_max_per_minute=1)

    for _ in range(5):
        assert client.post(
            SECURITY_POLICY, {"audit_log": False}, content_type="application/json"
        ).status_code == 200


def test_reads_are_never_limited():
    client = staff_client()
    arm(admin_write_rate_limit=True, admin_write_max_per_minute=1)

    for _ in range(5):
        assert client.get(POLICY).status_code == 200


def test_writes_past_the_ceiling_are_asked_to_wait():
    client = staff_client()
    arm(admin_write_rate_limit=True, admin_write_max_per_minute=1)

    codes = [
        client.post(
            SECURITY_POLICY, {"audit_log": False}, content_type="application/json"
        ).status_code
        for _ in range(3)
    ]

    assert codes[0] == 200
    assert 429 in codes
    assert client.post(
        SECURITY_POLICY, {"audit_log": False}, content_type="application/json"
    ).json()["code"] == "rate_limited"


# --------------------------------------------------------------------------
# B4 — the policy the Nuxt server attaches to the HTML
# --------------------------------------------------------------------------


def test_the_csp_endpoint_says_nothing_while_the_mode_is_off():
    arm(csp_mode=CspMode.OFF)

    body = Client().get(CSP).json()

    assert body["mode"] == CspMode.OFF
    assert body["header"] == ""
    assert body["value"] == ""


@pytest.mark.parametrize(
    "mode,header",
    [
        (CspMode.REPORT, "Content-Security-Policy-Report-Only"),
        (CspMode.ENFORCE, "Content-Security-Policy"),
    ],
)
def test_the_csp_endpoint_names_the_header_the_panel_should_send(mode, header):
    arm(csp_mode=mode)

    body = Client().get(CSP).json()

    assert body["header"] == header
    assert "default-src" in body["value"]


def test_the_csp_endpoint_is_readable_without_signing_in():
    """It reports a header a browser would receive anyway, and the Nuxt server
    reads it before anyone has a session."""
    arm(csp_mode=CspMode.ENFORCE)

    assert Client().get(CSP).status_code == 200
