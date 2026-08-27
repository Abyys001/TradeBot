"""The three controls that have to see every request — and the fast way out.

Anything that runs per request runs on the order-routing request too, which is
the one path this platform measures in milliseconds. So the shape here is a
guard clause, not a pipeline:

    values = flags.peek()          # a dict already in this process
    if not values["_middleware_active"]:
        return get_response(request)

With nothing switched on that is a dictionary lookup and a branch — no cache
round trip, no query, no thread hand-off. ``tests/test_security_cost.py`` pins
it by asserting the query count of ``/positions/`` and the routing endpoints is
the same with every switch on as with every switch off.

Written for both stacks because the panel runs under ASGI, for the same reason
``apps.accounts.sessions`` is: a sync-only middleware would put every request
through a thread hand-off, which is precisely the cost being avoided.
"""

from __future__ import annotations

import ipaddress
import time

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.contrib.auth import logout
from django.http import JsonResponse
from django.utils.decorators import sync_and_async_middleware

from apps.security import flags
from apps.security.audit import record
from apps.security.models import SecurityEventKind

#: Recorded at sign-in; the anchor for the absolute session age.
LOGIN_AT_KEY = "_panel_login_at"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Reachable even from an address the allowlist does not know.
#:
#: ``stop-all`` is on this list deliberately. The halt is the thing an operator
#: needs *most* when they cannot get in — a phone on a different network, a
#: position running at leverage — and a lock-out that also disables the brake is
#: the failure this whole layer is designed around. It is still staff-only.
ALLOWLIST_EXEMPT = (
    "/api/health/",
    "/api/security/csp/",
    "/api/trading/stop-all/",
)

#: Never rate limited, whatever the switch says: these are the money path.
ROUTING_PREFIXES = (
    "/api/trading/orders/",
    "/api/trading/balances/",
    "/api/trading/stop-all/",
    "/api/bots/",
)


def _allowed(ip: str | None, networks) -> bool:
    if not ip:
        # An address we could not parse is not an address on the list. The
        # production stack always has Caddy in front setting the header, so
        # this means something unusual is talking to us.
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


def _blocked(detail: str, code: str, status: int, **extra) -> JsonResponse:
    return JsonResponse({"detail": detail, "code": code, **extra}, status=status)


def _check_allowlist(request, values):
    if any(request.path.startswith(prefix) for prefix in ALLOWLIST_EXEMPT):
        return None
    from apps.accounts.sessions import client_ip

    if _allowed(client_ip(request), values["_allowed_networks"]):
        return None
    record(SecurityEventKind.IP_BLOCKED, request, detail={"path": request.path})
    return _blocked(
        "this address is not allowed to reach the panel", "ip_not_allowed", 403
    )


def _check_session_age(request, values):
    """Absolute age, then a rolling idle window Django itself enforces.

    ``set_expiry`` writes the new deadline into the session, so the cookie's
    own expiry does the work on the next request — there is no second clock to
    keep, and a browser closed for longer than the window comes back signed
    out. The cost is one session write per request, which is why it happens
    only while the switch is on.
    """
    session = getattr(request, "session", None)
    if session is None or not session.get("_auth_user_id"):
        return None

    started = session.get(LOGIN_AT_KEY)
    if started:
        age = time.time() - float(started)
        if age > float(values["session_max_hours"]) * 3600:
            record(
                SecurityEventKind.SESSION_EXPIRED,
                request,
                detail={"reason": "max_age", "hours": values["session_max_hours"]},
            )
            logout(request)
            return _blocked("this session has reached its maximum age", "session_expired", 401)

    session.set_expiry(int(values["idle_timeout_minutes"]) * 60)
    return None


def _check_write_rate(request, values):
    if request.method in SAFE_METHODS or not request.path.startswith("/api/"):
        return None
    if any(request.path.startswith(prefix) for prefix in ROUTING_PREFIXES):
        return None

    from apps.accounts.sessions import client_ip
    from apps.security import ratelimit

    bucket = f"write:{client_ip(request) or 'unknown'}"
    if not ratelimit.over_rate(bucket, per_minute=int(values["admin_write_max_per_minute"])):
        return None
    record(SecurityEventKind.RATE_LIMITED, request, detail={"path": request.path})
    return _blocked("too many changes in a short time — wait a moment", "rate_limited", 429)


def _pre(request, values):
    """Everything that can refuse a request, cheapest refusal first."""
    if values["ip_allowlist"]:
        response = _check_allowlist(request, values)
        if response is not None:
            return response

    if values["idle_timeout"]:
        response = _check_session_age(request, values)
        if response is not None:
            return response

    if values["admin_write_rate_limit"]:
        response = _check_write_rate(request, values)
        if response is not None:
            return response

    return None


@sync_and_async_middleware
def security_middleware(get_response):
    if iscoroutinefunction(get_response):

        async def middleware(request):
            values = flags.peek()
            if values is None:
                # The in-process snapshot expired. Refresh it off the event
                # loop — the cache read is small, but a blocking call on the
                # loop is what the fan-out cannot afford.
                values = await sync_to_async(flags.policy, thread_sensitive=True)()
            if not values["_middleware_active"]:
                return await get_response(request)
            blocked = await sync_to_async(_pre, thread_sensitive=True)(request, values)
            return blocked if blocked is not None else await get_response(request)

    else:

        def middleware(request):
            values = flags.policy()
            if not values["_middleware_active"]:
                return get_response(request)
            return _pre(request, values) or get_response(request)

    return middleware
