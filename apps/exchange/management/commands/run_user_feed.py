"""Long-running Hyperliquid private user WebSocket feed."""
from django.core.management.base import BaseCommand

from apps.exchange.user_ws import run_user_feed


class Command(BaseCommand):
    help = "Subscribe to Hyperliquid private channels (orderUpdates/userFills) and sync OrderRecord lifecycle."

    def handle(self, *args, **options):
        self.stdout.write("Starting Hyperliquid user feed (Ctrl+C to stop)...")
        run_user_feed()

