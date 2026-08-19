from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

ACCOUNTS = [
    (
        "masoud",
        "WalletManager21@@!",
        "DEPLOY_MASOUD_PASSWORD",
        {"is_staff": True, "is_superuser": True},
    ),
    (
        "siavash",
        "sia2680",
        "DEPLOY_SIAVASH_PASSWORD",
        {"is_staff": True, "is_superuser": False},
    ),
]


class Command(BaseCommand):
    help = "Create or update deploy accounts."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--keep-passwords",
            action="store_true",
            help="Leave existing passwords untouched; only fix flags.",
        )

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        keep = options["keep_passwords"]

        for username, default_pw, env_var, flags in ACCOUNTS:
            password = os.getenv(env_var, default_pw)
            user, created = User.objects.get_or_create(username=username)

            for attr, value in flags.items():
                setattr(user, attr, value)

            if not keep:
                user.set_password(password)

            user.save()

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created user {username!r}.")
                )
            else:
                action = "flags" if keep else "password and flags"
                self.stdout.write(
                    self.style.SUCCESS(f"Updated {action} for {username!r}.")
                )

        self.stdout.write("Deploy accounts ready.")
