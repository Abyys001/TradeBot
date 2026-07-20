"""Long-running background resampler — Node C (Master Plan §0.2, §3.2).

Reads raw trades from the append-only ledger, resamples to fixed and calendar
timeframes, writes Parquet + PG, publishes quality to Redis. Runs as a
separate OS process from Node B.
"""
import asyncio

from django.core.management.base import BaseCommand

from apps.exchange.resampler import run_resampler


class Command(BaseCommand):
    help = "Background resampler: raw trades → base TFs + quality metadata."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols", nargs="*", default=None,
            help="Markets to resample. Defaults to TABDEAL_INGEST_SYMBOLS.",
        )
        parser.add_argument(
            "--interval", type=float, default=60.0,
            help="Resample interval in seconds (default: 60).",
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting background resampler (Ctrl+C to stop)...")
        asyncio.run(run_resampler(
            symbols=options["symbols"],
            interval_s=options["interval"],
        ))
