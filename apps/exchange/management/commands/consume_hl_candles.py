"""Redis Pub/Sub consumer for Hyperliquid closed candles."""
from django.core.management.base import BaseCommand

from apps.exchange.candle_consumer import run_consumer


class Command(BaseCommand):
    help = "Subscribe to hl:candles:* and enqueue process_live_bar_task per strategy."

    def handle(self, *args, **options):
        self.stdout.write("Starting HL candle consumer (Ctrl+C to stop)...")
        run_consumer()
