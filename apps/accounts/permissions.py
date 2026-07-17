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


class IsInvestor(BasePermission):
    """Allow only authenticated investors."""

    message = "Investor role required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user and user.is_authenticated and user.role == User.Role.INVESTOR
        )
