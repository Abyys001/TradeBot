"""One shared login, several browsers: the dashboard has to show all of them.

Everyone signs in as the same staff user, so the "signed in" card is the only
surface where a second person holding that password becomes visible. These
tests pin what it is allowed to show and what it must never store.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.accounts.models import PanelSession
from apps.accounts.sessions import ONLINE_SECONDS, active_sessions

PASSWORD = "pw12345!"


def _staff() -> User:
    return User.objects.create_user("admin", password=PASSWORD, is_staff=True)


def _login(client: Client, agent: str = "", ip: str = "203.0.113.10") -> None:
    assert (
        client.post(
            "/api/accounts/auth/login/",
            data={"username": "admin", "password": PASSWORD},
            content_type="application/json",
            HTTP_USER_AGENT=agent,
            REMOTE_ADDR=ip,
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_two_browsers_on_one_login_are_two_rows():
    _staff()
    first, second = Client(), Client()
    _login(first, "Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537", "203.0.113.10")
    _login(second, "Mozilla/5.0 (iPhone) Safari/605", "198.51.100.4")

    body = first.get("/api/accounts/auth/sessions/").json()
    assert body["count"] == 2
    assert {row["username"] for row in body["sessions"]} == {"admin"}
    assert {row["ip_address"] for row in body["sessions"]} == {"203.0.113.10", "198.51.100.4"}
    assert {row["device"] for row in body["sessions"]} == {"Chrome · Windows", "Safari · iPhone"}
    # The caller's own row is flagged, never omitted.
    assert [row["current"] for row in body["sessions"]].count(True) == 1


@pytest.mark.django_db
def test_the_session_key_itself_is_never_stored():
    """The row must not be a ready-made login for anyone reading the database."""
    _staff()
    client = Client()
    _login(client)
    key = client.cookies["sessionid"].value
    row = PanelSession.objects.get()
    assert key not in row.session_hash
    assert row.session_hash == PanelSession.hash_key(key)
    assert not any(key in str(value) for value in row.__dict__.values())


@pytest.mark.django_db
def test_logging_out_drops_the_row_from_the_card():
    _staff()
    client = Client()
    _login(client)
    assert active_sessions().count() == 1

    assert client.post("/api/accounts/auth/logout/").status_code == 200
    assert active_sessions().count() == 0
    assert PanelSession.objects.get().ended_at is not None


@pytest.mark.django_db
def test_a_quiet_browser_is_idle_rather_than_online():
    """Last seen is the honest signal: a closed laptop is not "someone is here"."""
    _staff()
    client = Client()
    _login(client)
    PanelSession.objects.update(
        last_seen_at=timezone.now() - timezone.timedelta(seconds=ONLINE_SECONDS + 60)
    )

    row = client.get("/api/accounts/auth/sessions/").json()["sessions"][0]
    assert row["online"] is False


@pytest.mark.django_db
def test_the_proxy_header_is_used_for_the_address():
    """Behind Caddy, REMOTE_ADDR is the proxy — the card would show one IP for all."""
    _staff()
    client = Client()
    assert (
        client.post(
            "/api/accounts/auth/login/",
            data={"username": "admin", "password": PASSWORD},
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="203.0.113.55, 10.0.0.2",
            REMOTE_ADDR="10.0.0.2",
        ).status_code
        == 200
    )
    assert PanelSession.objects.get().ip_address == "203.0.113.55"


@pytest.mark.django_db
def test_the_list_is_staff_only():
    User.objects.create_user("partner", password=PASSWORD)
    anonymous = Client()
    assert anonymous.get("/api/accounts/auth/sessions/").status_code in (401, 403)

    partner = Client()
    assert partner.login(username="partner", password=PASSWORD)
    assert partner.get("/api/accounts/auth/sessions/").status_code == 403
