"""Panel sessions — who is signed in, from where, and how recently.

Everyone signs in as the same staff user, so "who is on the panel" is a
question about *sessions*, not about users: one login name, several browsers.
This module keeps one row per browser session (``PanelSession``) and the
dashboard's "Signed in" card reads it.

Two things it deliberately does not do:

* it never stores the session key, only its hash — see ``PanelSession``;
* it does not write a row per request. The panel polls positions, tickers and
  notifications every few seconds from every open tab, so a naive "update
  last_seen on every request" is thousands of writes an hour to say nothing new.
  A cache flag throttles the update to one per session per ``TOUCH_SECONDS``.
"""

from __future__ import annotations

import ipaddress
from datetime import timedelta

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.decorators import sync_and_async_middleware

from apps.accounts.models import PanelSession

#: How often a still-open session rewrites its ``last_seen_at``.
TOUCH_SECONDS = 60
#: Beyond this a row is listed as idle rather than online. Short enough that a
#: closed laptop stops reading as "someone is at the panel right now".
ONLINE_SECONDS = 120


def client_ip(request: HttpRequest) -> str | None:
    """The caller's address, honouring the reverse proxy in front of us.

    ``X-Forwarded-For`` is caller-controlled in general; here it is trustworthy
    because the production stack never exposes Django to the host — every
    request arrives through Caddy, which sets the header itself (see
    ``docker-compose.prod.yml``). An unparseable value is dropped rather than
    stored, so the column always holds an address or nothing.
    """
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    candidate = forwarded or (request.META.get("REMOTE_ADDR") or "").strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _agent(request: HttpRequest) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:300]


def record_login(request: HttpRequest, user) -> None:
    """Open (or reopen) the row for the session ``login()`` just created."""
    key = request.session.session_key
    if not key:
        return
    PanelSession.objects.update_or_create(
        session_hash=PanelSession.hash_key(key),
        defaults={
            "username": user.get_username(),
            "user": user,
            "ip_address": client_ip(request),
            "user_agent": _agent(request),
            "last_seen_at": timezone.now(),
            "ended_at": None,
        },
    )


def record_logout(request: HttpRequest) -> None:
    """Close the row before ``logout()`` throws the session key away."""
    key = request.session.session_key
    if not key:
        return
    now = timezone.now()
    PanelSession.objects.filter(session_hash=PanelSession.hash_key(key), ended_at=None).update(
        ended_at=now, last_seen_at=now
    )


def touch(request: HttpRequest) -> None:
    key = getattr(request, "session", None) and request.session.session_key
    if not key or not getattr(request, "user", None) or not request.user.is_authenticated:
        return
    digest = PanelSession.hash_key(key)
    if cache.get(f"panelsession:{digest}"):
        return
    cache.set(f"panelsession:{digest}", 1, TOUCH_SECONDS)
    now = timezone.now()
    updated = PanelSession.objects.filter(session_hash=digest).update(
        last_seen_at=now, ended_at=None, ip_address=client_ip(request), user_agent=_agent(request)
    )
    if not updated:
        # A session that predates this table, or one created by the Django
        # admin's own login page: adopt it rather than leaving a signed-in
        # browser invisible on the card.
        PanelSession.objects.create(
            session_hash=digest,
            username=request.user.get_username(),
            user=request.user,
            ip_address=client_ip(request),
            user_agent=_agent(request),
            last_seen_at=now,
        )


def active_sessions() -> QuerySet[PanelSession]:
    """Sessions that could still be used: not logged out, cookie not expired.

    The cookie's own lifetime is the cut-off — a row older than that names a
    browser whose session Django would refuse anyway, and listing it would
    overstate who has access.
    """
    cutoff = timezone.now() - timedelta(seconds=settings.SESSION_COOKIE_AGE)
    return PanelSession.objects.filter(ended_at=None, last_seen_at__gte=cutoff)


@sync_and_async_middleware
def panel_session_middleware(get_response):
    """Keep ``last_seen_at`` current for whoever is holding a session.

    Written for both stacks because the panel runs under ASGI: a sync-only
    middleware would put every HTTP request through a thread hand-off, and the
    fan-out path is the one thing here that is measured in milliseconds.
    """
    if iscoroutinefunction(get_response):

        async def middleware(request):
            response = await get_response(request)
            await sync_to_async(touch, thread_sensitive=True)(request)
            return response

    else:

        def middleware(request):
            response = get_response(request)
            touch(request)
            return response

    return middleware


#: Enough to tell one browser from another on the card. Deliberately coarse:
#: the full user-agent string is kept on the row for anyone who needs it, but a
#: dashboard reads "Chrome on Windows", not a version vector.
_BROWSERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
    ("Firefox/", "Firefox"),
)
_PLATFORMS = (
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Windows", "Windows"),
    ("Macintosh", "macOS"),
    ("Linux", "Linux"),
)


def describe_agent(user_agent: str) -> str:
    if not user_agent:
        return ""
    browser = next((name for token, name in _BROWSERS if token in user_agent), "")
    platform = next((name for token, name in _PLATFORMS if token in user_agent), "")
    if browser and platform:
        return f"{browser} · {platform}"
    return browser or platform
