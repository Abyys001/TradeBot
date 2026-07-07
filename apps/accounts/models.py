from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user — defined from day one (swapping AUTH_USER_MODEL later is painful).

    `is_trading_enabled` is a per-user master kill-switch: when False, no
    strategy belonging to this user may place orders (enforced by the engine
    in a later phase).
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        INVESTOR = "investor", "Investor"

    created_at = models.DateTimeField(auto_now_add=True)
    is_trading_enabled = models.BooleanField(
        default=False,
        help_text="Master kill-switch. When off, no strategies may trade.",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.INVESTOR)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Force password change on next login (set when an admin creates/resets an account).",
    )

    def __str__(self):
        return self.get_username()
