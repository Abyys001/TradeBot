"""The health endpoint — the one thing a deploy can ask before anyone signs in.

Two properties matter and both are easy to lose in a later edit: it must answer
without a session (a container healthcheck has none), and it must not become a
place where an unauthenticated caller learns about the deployment.
"""

from __future__ import annotations

import pytest
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


def test_it_answers_without_a_session():
    response = Client().get("/api/health/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] is True
    assert body["checks"]["cache"] is True


def test_it_reports_only_whether_each_dependency_answered():
    """No versions, hostnames, settings or error strings. Booleans only.

    This endpoint is reachable by anyone who can reach the domain. The moment
    it carries a value instead of a verdict, it is reconnaissance.
    """
    body = Client().get("/api/health/").json()
    assert set(body) == {"status", "checks"}
    assert all(isinstance(value, bool) for value in body["checks"].values())


def test_a_dead_cache_makes_the_container_unhealthy():
    """503 rather than a cheerful 200, so Docker can act on it.

    The cache holds the spec §7 kill switch. One that silently drops writes is
    a halt that does not hold, so "a backend is configured" is not good enough
    — the check writes and reads back.
    """
    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
    ):
        response = Client().get("/api/health/")
    assert response.status_code == 503
    assert response.json()["checks"]["cache"] is False


def test_a_quiet_price_feed_does_not_fail_the_check():
    """A venue outage is not a container to restart.

    Routing does not need the public feed — a limit order carries its own
    price and adapters can price themselves — so this is reported, not fatal.
    """
    response = Client().get("/api/health/")
    assert response.status_code == 200
    assert response.json()["checks"]["market_feed"] is False
