"""Long-running Hyperliquid market data WebSocket feed."""
from django.core.management.base import BaseCommand

from apps.exchange.market_ws import run_feed


class Command(BaseCommand):
    help = "Subscribe to Hyperliquid candle channels and publish closed bars to Redis Pub/Sub."

    def handle(self, *args, **options):
        self.stdout.write("Starting Hyperliquid market feed (Ctrl+C to stop)...")
        run_feed()
