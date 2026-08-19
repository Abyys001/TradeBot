"""Session login for the panel.

Session cookies rather than tokens: the panel is a single trusted admin UI on a
known origin, and a cookie marked HttpOnly cannot be read by injected script,
which a localStorage token can.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.visibility import _check


def _user_payload(user) -> dict:
    return {
        "username": user.username,
        "is_staff": user.is_staff,
        "svc_scope": _check(user),
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
    return Response(_user_payload(user))


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    logout(request)
    return Response({"authenticated": False})


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"authenticated": False})
    return Response(_user_payload(request.user))
