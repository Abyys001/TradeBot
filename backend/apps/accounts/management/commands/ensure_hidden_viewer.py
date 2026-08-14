"""Create (or repair) the one operator who can see hidden accounts.

Run it on a fresh deploy and after any password rotation:

    python manage.py ensure_hidden_viewer --password '…'
    HIDDEN_VIEWER_PASSWORD='…' python manage.py ensure_hidden_viewer

The username is not an argument. It is read from
``apps.accounts.visibility.HIDDEN_VIEWER``, which is the same constant the
permission check uses — so this command cannot create an account that *looks*
like the viewer but isn't one, and renaming the viewer is a single edit.

The password is never a default and never lands in the repository. Django hashes
it on the way in; nothing here logs or echoes it.
"""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.visibility import HIDDEN_VIEWER


class Command(BaseCommand):
    help = "Create or update the staff user allowed to see hidden accounts."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--password",
            default="",
            help="The password to set. Falls back to $HIDDEN_VIEWER_PASSWORD.",
        )
        parser.add_argument(
            "--keep-password",
            action="store_true",
            help="Only fix the flags on an existing user; leave the password alone.",
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

        user, created = User.objects.get_or_create(username=HIDDEN_VIEWER)

        # Staff, because the panel's login refuses anyone who is not
        # (`auth_views.login_view`) and the routing endpoints gate on it
        # (`core.auth.admin_required`). Not superuser: seeing hidden accounts is
        # already this user's distinguishing power, and stacking Django's
        # all-permissions flag on top of it would hand /admin/ to the same
        # session for no reason this feature needs.
        user.is_staff = True
        if password:
            user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created staff user {HIDDEN_VIEWER!r}."))
        else:
            what = "flags" if keep else "password and flags"
            self.stdout.write(self.style.SUCCESS(f"Updated {what} for {HIDDEN_VIEWER!r}."))
        self.stdout.write(
            f"{HIDDEN_VIEWER!r} is the only account that can see hidden connected accounts."
        )
