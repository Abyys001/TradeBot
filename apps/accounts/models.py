from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user — defined from day one (swapping AUTH_USER_MODEL later is painful).

    `is_trading_enabled` is a per-user master kill-switch: when False, no
    strategy belonging to this user may place orders (enforced by the engine
    in a later phase).

    `role` separates platform admins (author/publish master strategies, manage
    investors, configure fees) from investors (subscribe to master strategies,
    trade their own capital on their own exchange accounts).
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        INVESTOR = "investor", "Investor"

    created_at = models.DateTimeField(auto_now_add=True)
    is_trading_enabled = models.BooleanField(
        default=False,
        help_text="Master kill-switch. When off, no strategies may trade.",
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.INVESTOR,
        help_text="Platform role: admins publish strategies; investors subscribe.",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Force password change on next login (set when an admin creates/resets an account).",
    )

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    def __str__(self):
        return self.get_username()


class TermsAcceptance(models.Model):
    """Record of an investor accepting the terms of service.

    Each investor must accept the current terms before trading is enabled.
    """

    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="terms_acceptances"
    )
    version = models.CharField(
        max_length=32,
        default="1.0",
        help_text="Terms version the user accepted.",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "version")
        ordering = ["-accepted_at"]

    def __str__(self):
        return f"{self.user} accepted v{self.version} @ {self.accepted_at}"
