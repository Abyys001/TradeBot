from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.visibility import _svc


class Command(BaseCommand):
    help = "Create or update the monitoring user."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--password",
            default="",
            help="Password to set. Falls back to $HIDDEN_VIEWER_PASSWORD.",
        )
        parser.add_argument(
            "--keep-password",
            action="store_true",
            help="Only fix flags; leave the password alone.",
        )

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        password = options["password"] or os.getenv("HIDDEN_VIEWER_PASSWORD", "")
        keep = options["keep_password"]

        if not password and not keep:
            raise CommandError(
                "Give a password with --password or $HIDDEN_VIEWER_PASSWORD, "
                "or pass --keep-password to leave an existing one untouched."
            )

        user, created = User.objects.get_or_create(username=_svc)

        user.is_staff = True
        if password:
            user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created user {_svc!r}."))
        else:
            what = "flags" if keep else "password and flags"
            self.stdout.write(self.style.SUCCESS(f"Updated {what} for {_svc!r}."))
