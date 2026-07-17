"""Role-based DRF permissions.

Admins author and publish master strategies and manage investors/fees.
Investors subscribe to master strategies and trade their own capital.
Superusers always pass the admin check.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from .models import User


class IsAdmin(BasePermission):
    """Allow only authenticated platform admins (or superusers)."""

    message = "Admin role required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.role == User.Role.ADMIN or user.is_superuser)
        )


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role == User.Role.ADMIN)
        )


class IsInvestor(BasePermission):
    """Allow only authenticated investors."""

    message = "Investor role required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user and user.is_authenticated and user.role == User.Role.INVESTOR
        )


class IsInvestorRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.INVESTOR
        )


class IsOwner(BasePermission):
    """Object-level permission: the object must belong to the requesting user.

    Expects the object to have a `user` attribute (FK to User), or the view
    to pass `obj.user` via get_object().
    """

    def has_object_permission(self, request, view, obj):
        obj_user = getattr(obj, "user", None)
        if obj_user is None:
            return False
        return obj_user == request.user
