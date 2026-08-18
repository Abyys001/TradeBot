"""Close open trades that no account can be holding.

The routing path now refuses to leave one behind (``services._retire_if_nothing
_open``); this is for the rows written before it did — an entry where every leg
was skipped by sizing or came back "no position was opened" still sits OPEN,
which makes the ticket refuse the next order ("a trade is already open") while
close reports there is nothing to send.

    python manage.py retire_empty_trades --dry-run
    python manage.py retire_empty_trades

Only trades where *every* leg is provably flat are touched: one filled leg, or
one leg the exchange never answered for, and the trade is left exactly as it
is — that one may be a live position at leverage.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.trading.models import Trade, TradeStatus
from apps.trading.services import SAT_OUT_CODES, retire_if_nothing_open


class Command(BaseCommand):
    help = "Close open trades whose every leg provably holds nothing."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be closed without writing anything.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        retired = 0
        for trade in Trade.objects.filter(status=TradeStatus.OPEN).prefetch_related("legs"):
            legs = list(trade.legs.all())
            if any(leg.ok or leg.error_code not in SAT_OUT_CODES for leg in legs):
                continue
            codes = ", ".join(sorted({leg.error_code for leg in legs}) or ["no legs"])
            self.stdout.write(f"trade {trade.id} {trade.symbol}: {len(legs)} leg(s) — {codes}")
            if not dry_run:
                retire_if_nothing_open(trade)
            retired += 1

        if not retired:
            self.stdout.write(self.style.SUCCESS("no empty open trades"))
            return
        verb = "would close" if dry_run else "closed"
        self.stdout.write(self.style.SUCCESS(f"{verb} {retired} trade(s)"))
