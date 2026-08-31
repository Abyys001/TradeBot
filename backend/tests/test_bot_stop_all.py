"""Q22 — "close-all and Stop-all stop every running bot".

`docs/bot-mode.md` calls this the most important line of the eight, and the
reason is one sentence: a halt that flattens positions while a bot is still
evaluating is a halt that re-enters ninety seconds later, which is not a halt.

The two named tests `docs/bot-plan.md` §5 asks for live here.
"""

from __future__ import annotations

import datetime

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.bots import supervisor
from apps.bots.models import Bot, BotRun, BotState, StopReason
from apps.trading import killswitch
from tests.bot_factory import make_bot, make_run

pytestmark = pytest.mark.django_db(transaction=True)


def running_bots(count: int = 3) -> list[Bot]:
    bots = []
    for index in range(count):
        bot = make_bot(name=f"bot-{index}", state=BotState.LIVE)
        make_run(bot)
        bots.append(bot)
    return bots


def states() -> list[str]:
    return list(Bot.objects.order_by("id").values_list("state", flat=True))


def open_runs() -> int:
    return BotRun.objects.filter(stopped_at__isnull=True).count()


# --- the named test ---------------------------------------------------------


def test_stop_all_stops_every_running_bot():
    running_bots(3)
    stopped = supervisor.stop_all_sync(reason=StopReason.HALT, detail="test")
    assert len(stopped) == 3
    assert states() == [BotState.STOPPED] * 3
    assert open_runs() == 0


def test_turning_the_halt_on_stops_every_running_bot():
    """The wiring Q22 asks for: `killswitch.set_stop_all(True)` calls it."""
    running_bots(2)
    killswitch.set_stop_all(True, actor="test")
    assert states() == [BotState.STOPPED] * 2


def test_a_paper_bot_is_stopped_by_the_halt_too():
    """It is not routing real orders, but it is still deciding, and a run that
    kept deciding through a halt would diverge from every live bot beside it."""
    bot = make_bot(state=BotState.PAPER)
    make_run(bot)
    killswitch.set_stop_all(True, actor="test")
    bot.refresh_from_db()
    assert bot.state == BotState.STOPPED


def test_a_draft_bot_is_not_touched():
    bot = make_bot(state=BotState.DRAFT)
    supervisor.stop_all_sync(reason=StopReason.HALT)
    bot.refresh_from_db()
    assert bot.state == BotState.DRAFT


def test_an_already_stopped_bot_is_not_stopped_twice():
    bot = make_bot(state=BotState.STOPPED)
    assert supervisor.stop_all_sync(reason=StopReason.HALT) == []
    bot.refresh_from_db()
    assert bot.state == BotState.STOPPED


def test_the_stop_reason_is_recorded_on_the_run():
    bots = running_bots(1)
    supervisor.stop_all_sync(reason=StopReason.HALT, detail="close-all was pressed")
    run = BotRun.objects.get(bot=bots[0])
    assert run.stop_reason == StopReason.HALT
    assert "close-all" in run.stop_detail


def test_stopping_with_nothing_running_is_not_an_error():
    assert supervisor.stop_all_sync(reason=StopReason.HALT) == []


def test_the_halt_writes_the_state_rather_than_relying_on_a_live_task():
    """The halt is flipped from a DRF view on a worker thread, where there is no
    event loop to await a cancellation on. `Bot.state` is the authority."""
    bots = running_bots(1)
    supervisor.stop_all_sync(reason=StopReason.HALT)
    bots[0].refresh_from_db()
    assert bots[0].dry_run is True


# --- the second named test --------------------------------------------------


def test_a_stopped_bot_does_not_re_enter_after_a_flatten():
    """The whole point of the first test. Once stopped, the bot is not in the
    set `resume_all` would restart, and `lifecycle` will not put it back into
    `live` without going through paper."""
    from apps.bots import lifecycle
    from apps.bots.lifecycle import IllegalTransition

    bot = make_bot(state=BotState.LIVE)
    make_run(bot)
    supervisor.stop_all_sync(reason=StopReason.HALT, detail="close-all was pressed")
    bot.refresh_from_db()

    assert bot.id not in {b.id for b in supervisor._bots_to_resume()}
    with pytest.raises(IllegalTransition):
        lifecycle.transition(bot, BotState.LIVE)


def test_clearing_the_halt_does_not_restart_what_it_stopped():
    """Q25's second half applies to the halt too: none of this auto-resumes."""
    bots = running_bots(2)
    killswitch.set_stop_all(True, actor="test")
    killswitch.set_stop_all(False, actor="test")
    for bot in bots:
        bot.refresh_from_db()
        assert bot.state == BotState.STOPPED


def test_resume_all_only_picks_up_bots_whose_state_says_to_run():
    make_bot(name="stopped one", state=BotState.STOPPED)
    live = make_bot(name="live one", state=BotState.LIVE)
    paper = make_bot(name="paper one", state=BotState.PAPER)
    ids = {b.id for b in supervisor._bots_to_resume()}
    assert ids == {live.id, paper.id}


# --- the async surface ------------------------------------------------------


async def test_stop_all_is_callable_from_the_event_loop_too():
    """`route_close_all` awaits it before it closes anything."""
    await sync_to_async(running_bots)(2)
    stopped = await supervisor.stop_all(reason=StopReason.HALT, detail="close-all")
    # Nothing is actually running in this process, so no task is cancelled —
    # what matters is that the call is awaitable and does not raise.
    assert stopped == []


async def test_stopping_a_bot_that_is_not_running_is_safe():
    bots = await sync_to_async(running_bots)(1)
    await supervisor.stop(bots[0].id, reason=StopReason.MANUAL, detail="")
    run = await sync_to_async(BotRun.objects.get)(bot=bots[0])
    assert run.stopped_at is not None


# --- one bot at a time, even across a crash -----------------------------


async def test_resume_all_starts_only_the_most_recent_of_several_running_bots():
    """Only one bot may run at a time (enforced on every `start` — see
    `bots.views.start_bot`), but a restart re-reads `Bot.state` rather than
    trusting it: two rows left `paper`/`live` from before this rule existed
    must not both come back."""
    older = await sync_to_async(make_bot)(name="older", state=BotState.LIVE)
    await sync_to_async(make_run)(older)
    newer = await sync_to_async(make_bot)(name="newer", state=BotState.PAPER)
    await sync_to_async(make_run)(newer)
    # `make_bot`/`make_run` land in the same instant on a fast test run, so the
    # tie-break needs a real gap between the two `updated_at` values.
    await sync_to_async(Bot.objects.filter(id=older.id).update)(
        updated_at=timezone.now() - datetime.timedelta(minutes=1)
    )

    resumed = await supervisor.resume_all()

    assert resumed == [newer.id]
    await sync_to_async(older.refresh_from_db)()
    await sync_to_async(newer.refresh_from_db)()
    assert older.state == BotState.STOPPED
    assert newer.state == BotState.PAPER
    old_run = await sync_to_async(BotRun.objects.get)(bot=older)
    assert old_run.stopped_at is not None
    assert old_run.stop_reason == StopReason.MANUAL
