"""Block until PostgreSQL answers, so `migrate` can never race it.

Compose's `depends_on: service_healthy` covers a cold start, but not a restart
where the container is already up and the server is still replaying WAL — there
the backend wins the race, `migrate` dies on connection refused, and the whole
stack comes up 502 for a reason nobody looks for in the database logs.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Wait until the default database accepts connections."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--timeout",
            type=float,
            default=60.0,
            help="Seconds to keep trying before giving up (default: 60).",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=1.0,
            help="Seconds between attempts (default: 1).",
        )

    def handle(self, *args, **options) -> None:
        deadline = time.monotonic() + options["timeout"]
        attempt = 0
        last: Exception | None = None

        while time.monotonic() < deadline:
            attempt += 1
            connection = connections["default"]
            try:
                connection.ensure_connection()
            except OperationalError as exc:
                last = exc
                # A half-open connection from the failed attempt would be reused
                # on the next one and fail the same way without ever retrying.
                connection.close()
                if attempt == 1:
                    self.stdout.write("waiting for the database…")
                time.sleep(options["interval"])
                continue
            self.stdout.write(self.style.SUCCESS(f"database ready after {attempt} attempt(s)"))
            return

        raise CommandError(f"database not reachable within {options['timeout']}s: {last}")
