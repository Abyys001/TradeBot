"""Keep the platform's record and the exchanges' positions in agreement.

    python manage.py sync_positions            # loop forever, every few seconds
    python manage.py sync_positions --once     # one sweep, then exit
    python manage.py sync_positions --interval 5

``/positions/`` runs the same sweep whenever a panel polls it, which covers the
admin sitting in front of the screen. This is the half that does not depend on
anyone looking: a stop that fires at 3am, a liquidation over the weekend, or a
close that left one account untouched has to be reconciled whether or not a
browser is open, because the account stays blocked from the next trade until it
is — and because a position nobody can see is the worst thing this platform can
hold.

Read-only against the exchanges: it calls ``get_position`` and writes the
database. It never places, amends, or cancels an order.
"""

from __future__ import annotations

import asyncio
import time

from django.core.management.base import BaseCommand, CommandError

from apps.trading.possync import SYNC_INTERVAL, sync_positions


class Command(BaseCommand):
    help = "Reconcile open positions against every exchange, on a timer."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=float,
            default=SYNC_INTERVAL,
            help=f"Seconds between sweeps (default {SYNC_INTERVAL}).",
        )
        parser.add_argument(
            "--once", action="store_true", help="Run a single sweep and exit."
        )

    def handle(self, *args, **options) -> None:
        interval = options["interval"]
        if interval <= 0:
            raise CommandError("--interval must be greater than zero")
        if options["once"]:
            self._report(asyncio.run(sync_positions(force=True, deep=True)))
            return
        asyncio.run(self._loop(interval))

    async def _loop(self, interval: float) -> None:
        self.stdout.write(f"position sync every {interval}s — ctrl-c to stop")
        while True:
            started = time.monotonic()
            try:
                report = await sync_positions(force=True)
            except Exception as exc:  # noqa: BLE001 - the loop outlives one bad sweep
                self.stderr.write(self.style.ERROR(f"sweep failed: {exc}"))
            else:
                if report.changed:
                    self._report(report)
            # Sleep the remainder, so a slow exchange stretches the gap rather
            # than queueing sweeps behind each other.
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))

    def _report(self, report) -> None:
        if not report.changed:
            self.stdout.write(self.style.SUCCESS("in sync"))
            return
        for account_id in report.closed:
            self.stdout.write(
                self.style.WARNING(
                    f"account {account_id}: closed on the exchange — leg marked closed"
                )
            )
        for account_id in report.adopted:
            self.stdout.write(
                self.style.WARNING(
                    f"account {account_id}: position found on the exchange — leg restored"
                )
            )
        for account_id in report.drifted:
            self.stdout.write(f"account {account_id}: size/entry corrected from the exchange")
        for row in report.untracked:
            self.stdout.write(
                self.style.ERROR(f"{row}: position belongs to no trade in this platform")
            )
        if report.reopened:
            self.stdout.write(self.style.ERROR(f"trade {report.reopened} reopened"))
        if report.trade_retired:
            self.stdout.write("open trade retired — no account holds anything")
