"""Download multi-year OHLCV history from Hyperliquid into local parquet files.

Example:
    python manage.py download_history --coins BTC ETH SOL --intervals 1h 4h \
        --start 2024-01-01 --network mainnet
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.exchange.history_download import DEFAULT_START, date_to_ms, download_history

_DEFAULT_START = DEFAULT_START


class Command(BaseCommand):
    help = "Download paginated OHLCV history from Hyperliquid into local parquet files."

    def add_arguments(self, parser):
        parser.add_argument("--coins", nargs="+", required=True)
        parser.add_argument("--intervals", nargs="+", required=True)
        parser.add_argument("--start", default=_DEFAULT_START, help="YYYY-MM-DD")
        parser.add_argument("--end", default=None, help="YYYY-MM-DD (default: now)")
        parser.add_argument("--network", default="mainnet")

    def handle(self, *args, **opts):
        try:
            start_ms = date_to_ms(opts["start"])
            end_ms = date_to_ms(opts["end"]) if opts["end"] else int(time.time() * 1000)
        except ValueError as exc:
            raise CommandError(f"bad date: {exc}") from exc

        outcome = download_history(
            opts["coins"],
            opts["intervals"],
            start_ms,
            end_ms,
            network=opts["network"],
            on_progress=self._log_progress,
        )

        for key, result in outcome["progress"].items():
            if result.get("status") == "done":
                lo = datetime.fromtimestamp(result["start_ts"] / 1000, tz=timezone.utc)
                hi = datetime.fromtimestamp(result["end_ts"] / 1000, tz=timezone.utc)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{key}: {result['bars']} rows [{lo:%Y-%m-%d} .. {hi:%Y-%m-%d}]"
                    )
                )
            elif result.get("status") == "empty":
                self.stdout.write(f"{key}: no data")
            elif result.get("status") == "skipped":
                self.stderr.write(self.style.WARNING(f"skip {key}: {result.get('error')}"))
            else:
                self.stderr.write(self.style.ERROR(f"{key}: {result.get('error', result['status'])}"))

    def _log_progress(self, key: str, result: dict):
        status = result.get("status")
        if status == "done":
            self.stdout.write(f"{key}: downloaded {result.get('bars')} bars")
