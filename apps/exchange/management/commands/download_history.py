"""Download multi-year OHLCV history from Hyperliquid into local parquet files.

Example:
    python manage.py download_history --coins BTC ETH SOL --intervals 1h 4h \
        --start 2024-01-01 --network mainnet
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.exchange.history_download import (
    DEFAULT_START,
    VALID_DATA_TYPES,
    date_to_ms,
    download_history,
)

_DEFAULT_START = DEFAULT_START


class Command(BaseCommand):
    help = "Download paginated OHLCV/funding/OI history from Hyperliquid into local parquet files."

    def add_arguments(self, parser):
        parser.add_argument("--coins", nargs="+", required=True)
        parser.add_argument("--intervals", nargs="+", required=True)
        parser.add_argument("--start", default=_DEFAULT_START, help="YYYY-MM-DD")
        parser.add_argument("--end", default=None, help="YYYY-MM-DD (default: now)")
        parser.add_argument("--network", default="mainnet")
        parser.add_argument(
            "--data-types",
            nargs="+",
            choices=list(VALID_DATA_TYPES),
            default=["ohlcv"],
            metavar="TYPE",
            help=f"Data types to download: {', '.join(VALID_DATA_TYPES)} (default: ohlcv)",
        )
        parser.add_argument(
            "--no-fallback",
            action="store_false",
            dest="fallback",
            default=True,
            help="Disable auto-fallback to coarser intervals when fine data is partial",
        )

    def handle(self, *args, **opts):
        try:
            start_ms = date_to_ms(opts["start"])
            end_ms = date_to_ms(opts["end"]) if opts["end"] else int(time.time() * 1000)
        except ValueError as exc:
            raise CommandError(f"bad date: {exc}") from exc

        self.stdout.write(
            f"Downloading {', '.join(opts['data_types'])} for {opts['coins']} "
            f"@ {opts['intervals']} from {opts['start']} on {opts['network']} …"
        )

        outcome = download_history(
            opts["coins"],
            opts["intervals"],
            start_ms,
            end_ms,
            network=opts["network"],
            data_types=opts["data_types"],
            fallback=opts["fallback"],
            on_progress=self._log_progress,
        )

        self._print_summary(outcome["progress"])

    def _print_summary(self, progress: dict) -> None:
        """Print a final table: pair | status | bars | date range."""
        col_key = max((len(k) for k in progress), default=8)
        col_key = max(col_key, 8)
        header = f"{'Pair':<{col_key}}  {'Status':<8}  {'Bars':>6}  {'Date range'}"
        self.stdout.write("")
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        for key, result in sorted(progress.items()):
            status = result.get("status", "?")
            bars = result.get("bars", "")
            date_range = ""
            if result.get("start_ts") and result.get("end_ts"):
                lo = datetime.fromtimestamp(result["start_ts"] / 1000, tz=timezone.utc)
                hi = datetime.fromtimestamp(result["end_ts"] / 1000, tz=timezone.utc)
                date_range = f"{lo:%Y-%m-%d} .. {hi:%Y-%m-%d}"
                fb = result.get("fallback")
                if fb:
                    parts = [f"{r['interval']}:{r['bars']}bars" for r in fb]
                    date_range += f"  (+fallback {', '.join(parts)})"

            line = f"{key:<{col_key}}  {status:<8}  {str(bars):>6}  {date_range}"
            if status == "done":
                self.stdout.write(self.style.SUCCESS(line))
            elif status == "partial":
                self.stdout.write(self.style.WARNING(line))
            elif status in ("failed", "empty"):
                note = result.get("error", "")
                self.stderr.write(self.style.ERROR(f"{line}  {note}"))
            else:
                self.stdout.write(line)

    def _log_progress(self, key: str, result: dict) -> None:
        status = result.get("status")
        bars = result.get("bars", 0)
        if status == "done":
            self.stdout.write(f"  {key}: {bars} bars downloaded")
        elif status == "partial":
            self.stdout.write(f"  {key}: {bars} bars (partial — retention limit hit)")
