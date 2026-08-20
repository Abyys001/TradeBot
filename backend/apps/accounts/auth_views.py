"""Session login for the panel.

Session cookies rather than tokens: the panel is a single trusted admin UI on a
known origin, and a cookie marked HttpOnly cannot be read by injected script,
which a localStorage token can.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.accounts.models import PanelSession
from apps.accounts.sessions import (
    ONLINE_SECONDS,
    active_sessions,
    describe_agent,
    record_login,
    record_logout,
)
from apps.accounts.visibility import _check


def _user_payload(user) -> dict:
    return {
        "username": user.username,
        "is_staff": user.is_staff,
        # Named to match the panel's auth store; it gates the hidden-account
        # toggle and badge only, never what the server returns.
        "can_see_hidden": _check(user),
        "authenticated": True,
    }


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
    user = authenticate(request, username=username, password=password)

    if user is None:
        # Deliberately vague: saying which half was wrong helps enumeration.
        return Response({"detail": "invalid username or password"}, status=401)
    if not user.is_staff:
        return Response({"detail": "this account cannot access the panel"}, status=403)

    login(request, user)
    # After `login()`: it cycles the session key, and the row is keyed on it.
    record_login(request, user)
    return Response(_user_payload(user))


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    # Before `logout()`, which discards the session key this row is keyed on.
    record_logout(request)
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
