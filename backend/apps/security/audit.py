"""Writing the access history — and, more often, not writing it.

Every call here is a no-op while ``SecurityPolicy.audit_log`` is off, checked
before anything is built. That is the whole contract of this layer restated in
one module: off means the work does not happen, not that it happens and the
result is thrown away.
"""

from __future__ import annotations

import logging

from django.db import DatabaseError

from apps.security.flags import policy
from apps.security.models import SecurityEvent, SecurityEventKind

logger = logging.getLogger(__name__)

#: How many events the panel's Security card shows without asking for more.
EVENT_LIMIT = 50


def _context(request) -> dict:
    if request is None:
        return {"ip_address": None, "user_agent": ""}
    from apps.accounts.sessions import client_ip

    return {
        "ip_address": client_ip(request),
        "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:300],
    }


def _write(kind: str, *, username: str, detail: dict, request=None) -> None:
    try:
        SecurityEvent.objects.create(
            kind=kind, username=username[:150], detail=detail or {}, **_context(request)
        )
    except DatabaseError:
        # An audit row that cannot be written must not take the request with
        # it. The event is still in the application log, which is where this
        # would be looked for after a database problem anyway.
        logger.exception("security: could not record %s", kind)


def record(kind: str, request=None, *, username: str = "", detail: dict | None = None) -> None:
    """Record one access event, if the operator asked for a log."""
    if not policy()["audit_log"]:
        return
    if not username and request is not None:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            username = user.get_username()
    _write(kind, username=username, detail=detail or {}, request=request)


#: Settings whose *value* never reaches the history — only the fact that it
#: moved. The allowlist's contents belong on the settings row, not in a history
#: a later reader might page through casually: a list of the addresses that can
#: reach the panel is a map, and this file is the one place it could leak into.
REDACTED = ("allowed_ips",)

_REDACTED = "(changed)"


def _readable(name: str, before, after) -> list[str]:
    if name in REDACTED:
        return [_REDACTED, _REDACTED]
    return [str(before), str(after)]


def record_policy_change(changed: dict, *, actor: str) -> None:
    """Record a change to the switches themselves. Never suppressed.

    A log that can be switched off without leaving the fact behind is not a
    log, so this one write ignores the flag. It happens when somebody saves the
    Settings page and at no other time.
    """
    _write(
        SecurityEventKind.POLICY_CHANGED,
        username=actor,
        # Booleans and small integers, and for everything in ``REDACTED`` the
        # name alone.
        detail={"changed": {name: _readable(name, *pair) for name, pair in changed.items()}},
    )


def recent(limit: int = EVENT_LIMIT) -> list[SecurityEvent]:
    return list(SecurityEvent.objects.all()[:limit])
