"""Session login for the panel.

Session cookies rather than tokens: the panel is a single trusted admin UI on a
known origin, and a cookie marked HttpOnly cannot be read by injected script,
which a localStorage token can.

Everything the optional security layer adds to this file is behind a switch
that is off by default (``docs/security-plan.md``). With all of them off the
sequence is exactly what it was: authenticate, check staff, ``login()``, record
the session. Each ``if`` below is the guard clause that keeps it that way.
"""

from __future__ import annotations

import secrets
import time

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.accounts.models import Notification, PanelSession
from apps.accounts.sessions import (
    ONLINE_SECONDS,
    active_sessions,
    client_ip,
    describe_agent,
    end_other_sessions,
    end_sessions,
    looks_new,
    record_login,
    record_logout,
)
from apps.accounts.visibility import _check
from apps.security import flags, ratelimit, totp
from apps.security.audit import record
from apps.security.middleware import LOGIN_AT_KEY
from apps.security.models import SecurityEventKind

#: How long a half-finished sign-in waits for its second factor.
CHALLENGE_TTL = 300
_CHALLENGE_PREFIX = "security:mfa"


def _user_payload(user) -> dict:
    return {
        "username": user.username,
        "is_staff": user.is_staff,
        # Named to match the panel's auth store; it gates the hidden-account
        # toggle and badge only, never what the server returns.
        "can_see_hidden": _check(user),
        "authenticated": True,
    }


def _bucket(request, username: str) -> str:
    return f"login:{client_ip(request) or 'unknown'}:{username[:60]}"


def _rate_limited(request, username: str, values: dict):
    """The cooling-off period, if this caller is inside one."""
    if not values["login_rate_limit"]:
        return None
    waiting = ratelimit.locked_for(_bucket(request, username))
    if not waiting:
        return None
    record(SecurityEventKind.LOGIN_LOCKED, request, username=username)
    return Response(
        {
            "detail": "too many failed attempts — try again shortly",
            "code": "rate_limited",
            "retry_after": waiting,
        },
        status=429,
    )


def _count_failure(request, username: str, values: dict) -> None:
    if not values["login_rate_limit"]:
        return
    ratelimit.register_failure(
        _bucket(request, username),
        limit=int(values["login_max_attempts"]),
        window=int(values["login_window_seconds"]),
        lockout=int(values["login_lockout_seconds"]),
    )


def _new_device_notice(request, user, digest: str) -> None:
    """Spec §4's notification model, used for access instead of a failed order.

    Persistent and manually dismissed, like every other notice on that card: a
    sign-in the operator did not make is exactly the thing that must not scroll
    away while nobody is looking.
    """
    where = client_ip(request) or "an unknown address"
    what = describe_agent(request.META.get("HTTP_USER_AGENT", "")) or "an unrecognised browser"
    Notification.objects.create(
        account=None,
        code="new_device",
        message=f"New sign-in as {user.get_username()} from {where} on {what}.",
    )
    record(SecurityEventKind.NEW_DEVICE, request, username=user.get_username())


def _finish_login(request, user, *, remember: bool = False, factor: str = "") -> Response:
    """Everything that happens once the credentials are settled."""
    values = flags.policy()

    login(request, user)
    # After `login()`: it cycles the session key, and the row is keyed on it.
    digest = PanelSession.hash_key(request.session.session_key)
    request.session[LOGIN_AT_KEY] = time.time()
    record_login(request, user)

    fresh = looks_new(user.get_username(), request, exclude_hash=digest) if values[
        "new_device_notice"
    ] else False

    if values["single_session"]:
        ended = end_other_sessions(user.get_username(), keep_hash=digest)
        if ended:
            record(
                SecurityEventKind.SESSION_REVOKED,
                request,
                username=user.get_username(),
                detail={"reason": "single_session", "count": ended},
            )

    if fresh:
        _new_device_notice(request, user, digest)

    ratelimit.clear(_bucket(request, user.get_username()))
    record(
        SecurityEventKind.LOGIN_OK,
        request,
        username=user.get_username(),
        detail={"factor": factor} if factor else {},
    )

    response = Response(_user_payload(user))
    if remember and values["two_factor"] and values["trusted_devices"]:
        totp.remember(
            user,
            request,
            response,
            days=int(values["trusted_device_days"]),
            label=describe_agent(request.META.get("HTTP_USER_AGENT", "")),
        )
        record(SecurityEventKind.TRUST_ISSUED, request, username=user.get_username())
    return response


def _issue_challenge(user, remember: bool) -> str:
    token = secrets.token_urlsafe(24)
    cache.set(
        f"{_CHALLENGE_PREFIX}:{token}",
        {"user_id": user.pk, "remember": bool(remember)},
        CHALLENGE_TTL,
    )
    return token


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Hand the SPA a CSRF token before it posts anything."""
    return Response({"csrf_token": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    remember = bool(request.data.get("remember"))
    values = flags.policy()

    limited = _rate_limited(request, username, values)
    if limited is not None:
        return limited

    user = authenticate(request, username=username, password=password)

    if user is None:
        _count_failure(request, username, values)
        record(SecurityEventKind.LOGIN_FAILED, request, username=username)
        # Deliberately vague: saying which half was wrong helps enumeration.
        return Response({"detail": "invalid username or password"}, status=401)
    if not user.is_staff:
        _count_failure(request, username, values)
        record(SecurityEventKind.LOGIN_FAILED, request, username=username,
               detail={"reason": "not_staff"})
        return Response({"detail": "this account cannot access the panel"}, status=403)

    # The second factor, and the browser allowed to skip it. Both switches, and
    # the enrolment, have to be in place — a user with no enrolled device is let
    # through rather than stranded, which is why `flags.set_flags` refuses to
    # arm the switch until at least one staff account has one.
    if values["two_factor"] and totp.required_for(user):
        if values["trusted_devices"] and totp.is_trusted(user, request):
            return _finish_login(request, user, factor="trusted_device")
        return Response(
            {
                "mfa_required": True,
                "challenge": _issue_challenge(user, remember),
                "recovery_available": True,
            }
        )

    return _finish_login(request, user, remember=remember)


@api_view(["POST"])
@permission_classes([AllowAny])
def mfa_view(request):
    """The second half of a sign-in that asked for a code.

    The challenge, not the username, identifies the attempt: the password was
    already accepted, and re-posting it here would mean the panel holding it in
    memory for the length of a code entry.
    """
    token = str(request.data.get("challenge", ""))
    code = str(request.data.get("code", ""))
    key = f"{_CHALLENGE_PREFIX}:{token}"
    pending = cache.get(key) if token else None

    if not pending:
        return Response(
            {"detail": "that sign-in expired — start again", "code": "challenge_expired"},
            status=400,
        )

    user = User.objects.filter(pk=pending["user_id"], is_staff=True).first()
    if user is None:
        cache.delete(key)
        return Response({"detail": "that sign-in is no longer valid"}, status=400)

    values = flags.policy()
    limited = _rate_limited(request, user.get_username(), values)
    if limited is not None:
        return limited

    factor = totp.verify(user, code)
    if factor is None:
        _count_failure(request, user.get_username(), values)
        record(SecurityEventKind.MFA_FAILED, request, username=user.get_username())
        return Response({"detail": "that code is not right"}, status=401)

    cache.delete(key)
    record(
        SecurityEventKind.RECOVERY_USED if factor == "recovery" else SecurityEventKind.MFA_OK,
        request,
        username=user.get_username(),
    )
    remember = bool(request.data.get("remember", pending.get("remember")))
    return _finish_login(request, user, remember=remember, factor=factor)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    username = request.user.get_username() if request.user.is_authenticated else ""
    # Before `logout()`, which discards the session key this row is keyed on.
    record_logout(request)
    record(SecurityEventKind.LOGOUT, request, username=username)
    logout(request)
    return Response({"authenticated": False})


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"authenticated": False})
    return Response(_user_payload(request.user))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def sessions_view(request):
    """Spec §7-adjacent: who is signed in, on one shared login.

    The panel has one staff account by design, so the useful answer is not
    "which user" but "how many browsers hold that login, and where from". The
    caller's own row is flagged rather than hidden — a list that quietly omits
    you reads as one stranger too few.
    """
    now = timezone.now()
    current = request.session.session_key
    current_hash = PanelSession.hash_key(current) if current else ""
    rows = [
        {
            "id": session.id,
            "username": session.username,
            "ip_address": session.ip_address,
            "user_agent": session.user_agent,
            "device": describe_agent(session.user_agent),
            "started_at": session.started_at,
            "last_seen_at": session.last_seen_at,
            "online": (now - session.last_seen_at).total_seconds() <= ONLINE_SECONDS,
            "current": session.session_hash == current_hash,
        }
        for session in active_sessions()
    ]
    return Response({"sessions": rows, "count": len(rows)})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def revoke_session_view(request, pk: int):
    """End one of the browsers on that list.

    Not a switch, and not optional: the list of who holds the shared login has
    been on the dashboard since it was written, and being able to read it
    without being able to act on it was the gap.
    """
    session = PanelSession.objects.filter(pk=pk, ended_at=None).first()
    if session is None:
        return Response({"detail": "no such session"}, status=404)

    current = request.session.session_key
    if current and session.session_hash == PanelSession.hash_key(current):
        return Response(
            {"detail": "use sign out for this browser", "code": "own_session"}, status=400
        )

    end_sessions({session.session_hash})
    record(
        SecurityEventKind.SESSION_REVOKED,
        request,
        detail={"device": describe_agent(session.user_agent), "ip": session.ip_address},
    )
    return Response({"revoked": pk})
