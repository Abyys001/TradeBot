"""Liveness for the whole stack, in one unauthenticated request.

Deploying this thing means bringing up five containers that fail in ways the
panel cannot tell apart: a panel that loads but has no database behind it, a
Redis that is up but not the one the channel layer is pointed at, a feed that
is blocked outbound. Each of those looks, from a browser, like "the page is
slow" — and the runbook was six separate curls to find out which.

**What is deliberately absent:** versions, hostnames, settings values, counts,
error strings from the database. This endpoint is reachable without a session
(a container healthcheck has none), so it may say only *whether* each
dependency answered. `ok: false` is the whole diagnosis a stranger gets; the
detail is in the logs, where it is already.

`status` is 503 when the database or cache is down, because those are the two
the app cannot serve anything without — that is what makes it usable as a
Docker healthcheck. A dead price feed is reported but does **not** fail the
check: routing an order does not need the public feed (a limit order carries
its own price, and adapters can price themselves), so a venue outage must not
take a healthy container out of rotation.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)


def _database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:  # noqa: BLE001 - the answer is "no", whatever went wrong
        logger.exception("health: database unreachable")
        return False


def _cache() -> bool:
    """A real round trip through the cache, not just "a backend is configured".

    The kill switch lives here (spec §7). A cache that silently drops writes is
    a halt that does not hold, so this writes and reads back rather than
    trusting the setting.
    """
    try:
        cache.set("health:probe", "1", 10)
        return cache.get("health:probe") == "1"
    except Exception:  # noqa: BLE001
        logger.exception("health: cache unreachable")
        return False


def _feed() -> bool:
    """Whether any price provider has answered recently.

    Read from the cached round trip rather than probed, so a healthcheck on a
    ten-second interval cannot turn into ten calls a minute to an exchange.
    Null before anything has priced, which on a cold boot is normal — hence
    this not failing the check.
    """
    try:
        from apps.exchanges.marketdata import provider_latency

        return provider_latency()["ms"] is not None
    except Exception:  # noqa: BLE001
        return False


@never_cache
def health(request: HttpRequest) -> JsonResponse:
    checks = {
        "database": _database(),
        "cache": _cache(),
        # Redis-backed in production; in-memory means one process only, which
        # is worth seeing in a deploy that thought it had Redis.
        "channel_layer_shared": "redis" in str(
            settings.CHANNEL_LAYERS["default"]["BACKEND"]
        ).lower(),
        "market_feed": _feed(),
    }
    serving = checks["database"] and checks["cache"]
    return JsonResponse(
        {"status": "ok" if serving else "unavailable", "checks": checks},
        status=200 if serving else 503,
    )
