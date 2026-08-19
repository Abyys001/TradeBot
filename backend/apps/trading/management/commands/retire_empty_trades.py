"""Close open trades that no account can be holding.

The routing path now refuses to leave one behind (``services.retire_if_nothing
_open``, called from the entry, the positions sweep and close); this is for the
rows written before it did — an entry where every leg was skipped by sizing or
came back "no position was opened" still sits OPEN, which makes the ticket
refuse the next order ("a trade is already open") while close reports there is
nothing to send.

    python manage.py retire_empty_trades --dry-run
    python manage.py retire_empty_trades

Only trades where *every* leg is provably flat are touched: one leg the
exchange never answered for and the trade is left exactly as it is — that one
may be a live position at leverage.

    python manage.py retire_empty_trades --trade 42 --force

is the escape hatch for exactly that leg when the account cannot be reached at
all (credentials replaced, exchange delisted, adapter refuses to build), so
close can never settle it. It writes CLOSED over an unproven leg, which is the
one thing the rest of this codebase refuses to do — **check the exchange by
hand first**. It closes the platform's record, not a position.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.trading.models import Trade, TradeStatus
from apps.trading.services import leg_is_flat, retire_if_nothing_open


class Command(BaseCommand):
    help = "Close open trades whose every leg provably holds nothing."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be closed without writing anything.",
        )
        parser.add_argument(
            "--trade",
            type=int,
            help="Restrict to one trade id. Required with --force.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Close --trade even though a leg is unproven. Only after you "
                "have checked the exchange yourself: this closes the record, "
                "not the position."
            ),
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        trade_id = options["trade"]
        force = options["force"]
        if force and trade_id is None:
            raise CommandError("--force needs --trade <id>; it never runs over every trade")

        trades = Trade.objects.filter(status=TradeStatus.OPEN).prefetch_related("legs")
        if trade_id is not None:
            trades = trades.filter(pk=trade_id)

        retired = 0
        for trade in trades:
            legs = list(trade.legs.all())
            flat = all(leg_is_flat(leg) for leg in legs)
            if not flat and not force:
                continue
            codes = ", ".join(sorted({leg.error_code for leg in legs}) or ["no legs"])
            note = "" if flat else " — UNPROVEN, forced"
            self.stdout.write(
                f"trade {trade.id} {trade.symbol}: {len(legs)} leg(s) — {codes}{note}"
            )
            if not dry_run:
                if flat:
                    retire_if_nothing_open(trade)
                else:
                    self._force_close(trade)
            retired += 1

        if not retired:
            self.stdout.write(self.style.SUCCESS("no empty open trades"))
            return
        verb = "would close" if dry_run else "closed"
        self.stdout.write(self.style.SUCCESS(f"{verb} {retired} trade(s)"))

    def _force_close(self, trade: Trade) -> None:
        now = timezone.now()
        trade.legs.filter(closed_at__isnull=True).update(closed_at=now)
        trade.status = TradeStatus.CLOSED
        trade.closed_at = now
        trade.save(update_fields=["status", "closed_at"])
        self.stdout.write(
            self.style.WARNING(
                f"trade {trade.id} closed by hand — the exchange was never asked; "
                "confirm the account is flat there."
            )
        )
