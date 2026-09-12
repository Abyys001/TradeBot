"""The Telegram notifier.

    python manage.py run_telegram

Two loops in one process. One delivers: every couple of seconds it writes a
heartbeat, tails the log table from the stored cursor and sends what is new.
The other listens: a ``getUpdates`` long poll for ``/start`` links and the
read-only commands.

Its own failures go to stderr and ``TelegramBot.last_error`` — never through
the logger. A logged error is an event, and "could not reach Telegram" queued
for delivery to Telegram feeds itself for as long as Telegram is unreachable.

It also runs the credential-expiry sweep once an hour. That sweep otherwise
runs only when a panel polls balances, and this service exists for the hours
nobody has the panel open.
"""

from __future__ import annotations

import asyncio
import time

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.telegram import commands, sink
from apps.telegram.client import TelegramClient, TelegramError
from apps.telegram.models import TelegramBot

CREDENTIAL_SWEEP_SECONDS = 3600
ERROR_BACKOFF_SECONDS = 30.0


def _heartbeat() -> TelegramBot:
    # A long-lived process holds its connection for days; one the database has
    # since dropped would wedge every later query.
    close_old_connections()
    row = TelegramBot.load()
    TelegramBot.objects.filter(pk=row.pk).update(last_heartbeat_at=timezone.now())
    return row


def _load() -> TelegramBot:
    close_old_connections()
    return TelegramBot.load()


class Command(BaseCommand):
    help = "Deliver panel events to the linked Telegram chat and answer its commands."

    def handle(self, *args, **options) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        self.stdout.write("telegram notifier — ctrl-c to stop")
        await asyncio.gather(self._deliver(), self._listen())

    async def _fail(self, description: str) -> None:
        self.stderr.write(self.style.ERROR(f"telegram: {description}"))
        await sync_to_async(sink.record_error)(description)

    async def _deliver(self) -> None:
        poll = float(settings.TELEGRAM["POLL_SECONDS"])
        repeats = sink.Repeats()
        swept = 0.0
        while True:
            started = time.monotonic()
            delay = poll
            try:
                row = await sync_to_async(_heartbeat)()
                if started - swept > CREDENTIAL_SWEEP_SECONDS:
                    from apps.accounts.credentials import sync_notifications

                    await sync_to_async(sync_notifications)()
                    swept = started
                if row.enabled and row.linked and row.configured:
                    await sink.drain(TelegramClient(row.token), row, repeats)
            except TelegramError as exc:
                await self._fail(exc.description)
                delay = ERROR_BACKOFF_SECONDS
            except Exception as exc:  # noqa: BLE001 - the loop outlives one bad pass
                await self._fail(f"delivery pass failed ({type(exc).__name__})")
                delay = ERROR_BACKOFF_SECONDS
            await asyncio.sleep(max(0.0, delay - (time.monotonic() - started)))

    async def _listen(self) -> None:
        idle = float(settings.TELEGRAM["POLL_SECONDS"]) * 3
        while True:
            try:
                row = await sync_to_async(_load)()
                if not row.configured:
                    await asyncio.sleep(idle)
                    continue
                client = TelegramClient(row.token)
                updates = await client.get_updates(row.update_offset)
                for update in updates:
                    reply = await sync_to_async(commands.handle)(update)
                    await sync_to_async(commands.advance_offset)(int(update["update_id"]) + 1)
                    if reply is not None:
                        await sink.send(client, reply.chat_id, reply.text)
            except TelegramError as exc:
                # 409 is a second poller on the same token (another deployment,
                # or a webhook) — worth saying plainly, since it looks like a hang.
                await self._fail(exc.description)
                await asyncio.sleep(ERROR_BACKOFF_SECONDS)
            except Exception as exc:  # noqa: BLE001
                await self._fail(f"command poll failed ({type(exc).__name__})")
                await asyncio.sleep(ERROR_BACKOFF_SECONDS)
