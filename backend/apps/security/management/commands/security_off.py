"""The documented way back in.

Every control in ``apps/security`` can be cleared from a shell on the box
without a password, a browser, or a working second factor. That is deliberate:
anyone who can run this already has the database and the encryption keys, so it
gives away nothing — and the alternative is an operator locked out of a panel
holding live positions at three in the morning.

    python manage.py security_off                  # every switch off
    python manage.py security_off --flag two_factor
    python manage.py security_off --list

``SECURITY_FEATURES=false`` in the environment does the same thing without a
database write, and is the right answer when the database is the problem.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.security import flags


class Command(BaseCommand):
    help = "Turn security controls off. The lock-out escape hatch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flag",
            action="append",
            dest="names",
            help="Turn off one switch. Repeatable. Omit to turn every switch off.",
        )
        parser.add_argument(
            "--list", action="store_true", help="Show the switches and stop."
        )

    def handle(self, *args, **options):
        if options["list"]:
            state = flags.state()
            width = max(len(name) for name in flags.SWITCHES)
            for name in flags.SWITCHES:
                mark = "on " if state[name] else "off"
                self.stdout.write(f"  {mark}  {name.ljust(width)}")
            self.stdout.write(f"  {state['csp_mode']:<4} csp_mode")
            if not state["available"]:
                self.stdout.write(
                    self.style.WARNING("\n  SECURITY_FEATURES=false — every control is off.")
                )
            return

        names = options["names"] or list(flags.SWITCHES)
        unknown = [name for name in names if name not in flags.SWITCHES]
        if unknown:
            raise CommandError(f"not a switch: {', '.join(unknown)}")

        changes = {name: False for name in names}
        if not options["names"]:
            changes["csp_mode"] = "off"

        try:
            flags.set_flags(changes, actor="")
        except flags.PolicyError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"off: {', '.join(sorted(changes))}"))
