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

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    def __str__(self):
        return self.get_username()
