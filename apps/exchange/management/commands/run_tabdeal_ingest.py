"""Long-running Tabdeal FAPI trade ingest node (Master Plan §2, Node A).

Connects to the public trade broadcast, appends every trade to the append-only ledger
(authoritative history), and publishes to the Redis Stream seam for Node B. Run N≥2
replicas with distinct ``--node-id`` / ``INGEST_NODE_ID`` for gap redundancy (§0.1).
"""
from django.core.management.base import BaseCommand

from apps.exchange.ingest import run_ingest


class Command(BaseCommand):
    help = "Ingest Tabdeal futures trades into the append-only ledger + Redis Stream."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols", nargs="*", default=None,
            help="Markets to ingest, e.g. BTC_USDT ETH_USDT. Defaults to TABDEAL_INGEST_SYMBOLS.",
        )
        parser.add_argument(
            "--node-id", default=None,
            help="Ingest node id (ledger partition). Defaults to INGEST_NODE_ID or hostname.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting Tabdeal trade ingest (Ctrl+C to stop)...")
        run_ingest(symbols=options["symbols"], node_id=options["node_id"])
