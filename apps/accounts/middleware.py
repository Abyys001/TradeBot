"""Middleware to enforce forced password change on first login."""
from __future__ import annotations


from django.http import JsonResponse
from django.urls import resolve

# Paths that are always allowed even when must_change_password is True.
_ALWAYS_ALLOWED = {
    "csrf_token",
    "login",
    "logout",
    "change_password",
    "me",
}


class ForcePasswordChangeMiddleware:
    """Block authenticated users from non-exempt views until they change their password."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, "must_change_password", False)
        ):
            try:
                match = resolve(request.path_info)
                view_name = match.func.__name__ if hasattr(match.func, "__name__") else ""
                # Also check DRF viewset action names
                if hasattr(match.func, "actions"):
                    action_name = request.resolver_match.kwargs.get("action", "")
                    view_name = action_name or view_name
            except Exception:
                view_name = ""

            if view_name not in _ALWAYS_ALLOWED:
                return JsonResponse(
                    {"detail": "Password change required. Please update your password."},
                    status=403,
                )

        return self.get_response(request)
