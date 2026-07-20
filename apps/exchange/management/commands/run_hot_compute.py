"""Long-running hot-compute node — Node B (Master Plan §2, §3.3).

Consumes the Tabdeal trade stream from an acked cursor (crash-safe), aggregates
per active (symbol, timeframe) into sealed bars, tags each bar with a quality from
ledger coverage, and drives the live strategy runner in-process (no network hop on
the hot path). A SUSPECT/MISSING bar halts the strategy in the runner (invariant 1)
and triggers the §4.3 position policy.

Runs as its own OS process, separate from ingest (Node A) and the background
resampler (Node C), so a strategy crash or redeploy here cannot lose history.
"""
from django.core.management.base import BaseCommand

from apps.exchange.hot_compute import run_hot_compute


class Command(BaseCommand):
    help = "Run the Tabdeal hot-compute node: trade stream -> sealed bars -> strategy runner."

    def handle(self, *args, **options):
        self.stdout.write("Starting hot-compute node B (Ctrl+C to stop)...")
        run_hot_compute()
