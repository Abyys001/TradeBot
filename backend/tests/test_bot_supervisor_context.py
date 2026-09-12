"""A bot started from the panel has to outlive the request that started it.

This is the bug that made "the bot is LIVE and does nothing" the platform's
normal behaviour, and it never reached any order-routing code:

Django wraps every ASGI request in an ``asgiref`` ``ThreadSensitiveContext``,
and closes that context's executor as soon as the response is sent. The panel's
start button is an async view, so the supervisor task it created inherited the
request's context — and the first ``sync_to_async`` the bot made *after* the
response (``feed.check_clock()``, one call into warm-up and a long way from any
exchange) raised ``RuntimeError: CurrentThreadExecutor already quit or is
broken``. The task died, ``Bot.state`` stayed ``live``, and the panel went on
showing a running bot that had not evaluated a bar since it was pressed.

Every bot started from the panel had zero bars and zero actions. The one bot
that did work was the one the *process* resumed on start-up, outside any
request — which is why this looked like "bots only work after a restart".

The fix is in ``supervisor.start``: the task is created in a context of its
own. These tests pin it from both ends — the mechanism, and the symptom.
"""

from __future__ import annotations

import asyncio

import pytest
from asgiref.sync import ThreadSensitiveContext, async_to_sync, sync_to_async

from apps.bots import supervisor
from apps.bots.models import Bot, BotState
from tests.bot_factory import make_bot

pytestmark = pytest.mark.django_db(transaction=True)


async def _rename(bot_id: int, name: str) -> None:
    """Any thread-sensitive database write. The bot loop is made of these."""
    await sync_to_async(Bot.objects.filter(id=bot_id).update)(name=name)


@pytest.mark.asyncio
async def test_a_bot_started_inside_a_request_still_works_after_the_response(monkeypatch):
    """Start it the way the panel does, then end the request and let it run.

    The request is reproduced as Django actually assembles one: the handler's
    ``ThreadSensitiveContext``, a **sync** middleware adapted with
    ``sync_to_async``, and the async view reached back through
    ``async_to_sync`` — which is what puts a ``CurrentThreadExecutor`` in the
    context the task would otherwise inherit. That executor is what "already
    quit or is broken" refers to.
    """
    bot = await sync_to_async(make_bot)(state=BotState.LIVE)
    responded = asyncio.Event()
    reached = asyncio.Event()
    failed: list[BaseException] = []

    async def fake_run(bot_id: int, run_id: int) -> None:
        # A real bot's first database call comes a warm-up later; waiting here
        # is what puts this one on the far side of the response, which is the
        # only place the bug was ever visible.
        await responded.wait()
        try:
            await _rename(bot_id, "still alive")
        except BaseException as exc:  # noqa: BLE001 - the assertion is the point
            failed.append(exc)
        finally:
            reached.set()

    monkeypatch.setattr(supervisor, "_run_bot", fake_run)

    async def the_view() -> None:
        await supervisor.start(bot, actor="tester")

    def sync_middleware() -> None:
        async_to_sync(the_view)()

    async with ThreadSensitiveContext():
        await sync_to_async(sync_middleware)()
    # ...and the response is sent here, which shuts those executors down.
    responded.set()

    await asyncio.wait_for(reached.wait(), timeout=10)
    assert not failed, f"the bot task died after the response: {failed[0]!r}"
    assert await sync_to_async(
        lambda: Bot.objects.filter(id=bot.id).values_list("name", flat=True).first()
    )() == "still alive"

    await supervisor.stop(bot.id, reason="manual", actor="tester")


@pytest.mark.asyncio
async def test_the_task_does_not_inherit_the_requests_executor(monkeypatch):
    """The mechanism, stated directly: a bot's executor is never the caller's.

    Asserted rather than left implicit because the failure mode is silent —
    the context is inherited by default, and nothing about a
    ``create_task(...)`` call says which context it ran in.
    """
    bot = await sync_to_async(make_bot)(state=BotState.LIVE)
    seen: list[object | None] = []
    done = asyncio.Event()

    async def fake_run(bot_id: int, run_id: int) -> None:
        seen.append(_current_context())
        done.set()

    monkeypatch.setattr(supervisor, "_run_bot", fake_run)

    async with ThreadSensitiveContext():
        caller = _current_context()
        await supervisor.start(bot)
        await asyncio.wait_for(done.wait(), timeout=10)

    assert caller is not None
    assert seen == [seen[0]] and seen[0] is not caller

    await supervisor.stop(bot.id, reason="manual")


def _current_context():
    """The thread-sensitive context in force here, or None when there is none."""
    from asgiref.sync import SyncToAsync

    try:
        return SyncToAsync.thread_sensitive_context.get()
    except LookupError:
        return None
