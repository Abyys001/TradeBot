"""Run the bot supervisor as its own process.

    python manage.py run_bots            # supervise every paper/live bot
    python manage.py run_bots --once     # start them, report, and exit
    python manage.py run_bots --dry-run  # list what would be started

The default deployment does **not** need this: ``BOT_SUPERVISOR_IN_ASGI=true``
puts the supervisor in the ASGI process, alongside the fan-out it routes
through. This exists for the deployment that wants the separation — set
``BOT_SUPERVISOR_IN_ASGI=false`` and add a ``bots`` service beside ``possync``.

The trade-off is stated rather than hidden: out here, ``route_*`` still runs in
this process, so the spec §4 deadline is unaffected, but the WebSocket
broadcasts go through the channel layer to reach the panel, which is one hop
more than the in-ASGI arrangement.
"""

from __future__ import annotations

import asyncio
import contextlib

from django.core.management.base import BaseCommand

from apps.bots.models import Bot, BotState


class Command(BaseCommand):
    help = "Supervise every paper/live bot in this process."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true", help="Start them, report, exit.")
        parser.add_argument(
            "--dry-run", action="store_true", help="List what would be started, and stop."
        )
        parser.add_argument(
            "--poll",
            type=float,
            default=15.0,
            help="Seconds between checks for bots started elsewhere (default 15).",
        )

    def handle(self, *args, **options) -> None:
        pending = list(Bot.objects.filter(state__in=[BotState.PAPER, BotState.LIVE]))
        if options["dry_run"]:
            if not pending:
                self.stdout.write(self.style.WARNING("no bot is in paper or live"))
                return
            for bot in pending:
                self.stdout.write(f"would start {bot.id}: {bot.name} ({bot.symbol} {bot.interval})")
            return

        asyncio.run(self._run(once=options["once"], poll=options["poll"]))

    async def _run(self, *, once: bool, poll: float) -> None:
        from apps.bots import supervisor

        started = await supervisor.resume_all()
        self.stdout.write(self.style.SUCCESS(f"started {len(started)} bot(s)"))
        if once:
            await supervisor.shutdown()
            return

        self.stdout.write(f"supervising — rechecking every {poll}s, ctrl-c to stop")
        try:
            while True:
                await asyncio.sleep(poll)
                # A bot started from the panel while this process is running
                # would otherwise never get a task. Cheap: one indexed query.
                await supervisor.resume_all()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            # Cancel the tasks without writing a stop reason — this is a deploy,
            # not a fault, and the runs stay open so the Phase 7 soak survives it.
            with contextlib.suppress(Exception):
                await supervisor.shutdown()
