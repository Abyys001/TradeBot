"""Watchdog management command — runs the watchdog monitor loop."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the watchdog monitor (Node D)"

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=5.0, help="Check interval in seconds")

    def handle(self, *args, **options):
        import asyncio
        from apps.watchdog.monitor import run_watchdog

        asyncio.run(run_watchdog(interval_s=options["interval"]))
