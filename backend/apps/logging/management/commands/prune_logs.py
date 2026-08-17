"""Delete log entries older than N days.

Default retention is 30 days.  For cron:

    python manage.py prune_logs
    python manage.py prune_logs --days 7
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.logging.models import LogEntry


class Command(BaseCommand):
    help = "Delete log entries older than the given number of days."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete entries older than this many days (default: 30).",
        )

    def handle(self, *args, **options) -> None:
        days = options["days"]
        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
        self.stdout.write(f"Pruned {deleted} log entries older than {days} days.")
