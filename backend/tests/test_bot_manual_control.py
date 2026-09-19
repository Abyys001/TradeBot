"""Q41 — the operator's own hand on a running bot, and what follows from it.

Three things have to be true, and they are the three groups below.

  **The press is the bot's own order path.** Not a second one. A manual entry
  produces the same ``Trade``, stamped with the same run, sized by §5, fanned
  out to the accounts that opted into *bot* trading, recorded as a
  ``BotAction`` — the only difference from a bar-driven entry being that the
  row says a person is behind it.

  **A hand-opened position is the bot's to manage.** The strategy is told what
  is held before the next bar, so its own exit closes what the operator
  opened. That is the whole promise of the feature: intervention works *with*
  the strategy, not beside it.

  **A hand-closed position is not reopened behind the operator's back.** The
  hard half. A strategy whose entry condition is a state rather than a crossing
  asks to enter on every bar it holds, so "wait for the next entry signal"
  cannot mean "ignore one bar" — it has to mean the script stopped asking and
  asked again. The last group drives exactly that through the real loop.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.bots import desk, intervene, supervisor
from apps.bots.feed import FeedBar
from apps.bots.models import ActionType, BotAction, BotRun, BotState
from apps.bots.translate import Action
from apps.pine.intent import Side
from apps.trading import killswitch
from apps.trading.models import Trade, TradeStatus
from tests.bot_factory import make_bot
from tests.test_bot_live_bar import KEY, ScriptedFeed, _account, _bar

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

#: Enters on any green bar and closes on any red one. Both halves matter: the
#: entry is a *state* (every green bar asks again, which is what the re-entry
#: guard has to survive) and the exit is the signal a hand-opened position has
#: to be closed by.
SOURCE = """//@version=5
strategy("green in, red out", overlay=true)
if close > open
    strategy.entry("Long", strategy.long)
if close < open
    strategy.close("Long", comment = "Exit")
"""

#: One live bar at a time, chosen by the test. Warm-up comes from
#: ``ScriptedFeed`` and is every bar red, so nothing it discards would have
#: traded.
class StagedFeed(ScriptedFeed):
    live: list = []

    async def __aiter__(self):
        for bar in type(self).live:
            yield FeedBar(bar=bar, source="scripted", transport="poll")


@pytest.fixture
def staged(monkeypatch):
    from apps.exchanges import marketdata

    StagedFeed.live = []
    monkeypatch.setattr(supervisor, "BarFeed", StagedFeed)
    # The bar the gate compares against the live ticker. Green bars close at
    # 101; a feed that agrees with the market is what the drift check is for,
    # and not what any of this is about.
    monkeypatch.setattr(
        marketdata,
        "get_ticker",
        lambda **_: {"price": "101", "live": True, "source": "test"},
    )
    return StagedFeed


async def _bot(**kwargs):
    defaults = {
        "source": SOURCE,
        "state": BotState.LIVE,
        "symbol": "BTCUSDT",
        "interval": "30m",
        "sl_pct": "1",
        "tp_pct": "2",
    }
    return await sync_to_async(make_bot)(**{**defaults, **kwargs})


async def _open_run(bot) -> BotRun:
    return await supervisor._open_run(bot, actor="tester")


async def _bars(run: BotRun, bot, *indices_green) -> None:
    """Run the real loop over these bars, resuming the same run each time."""
    StagedFeed.live = [_bar(index, green=green) for index, green in indices_green]
    await supervisor._run_bot(bot.id, run.id)


@sync_to_async
def _trades() -> list[Trade]:
    return list(Trade.objects.order_by("id"))


@sync_to_async
def _reload(run: BotRun) -> BotRun:
    return BotRun.objects.get(id=run.id)


@sync_to_async
def _actions() -> list[tuple]:
    return [
        (row.action_type, row.ok, row.intent.get("origin", ""), bool(row.intent.get("held_off")))
        for row in BotAction.objects.order_by("id")
    ]


def _open(side: str = Side.LONG.value) -> Action:
    return Action(type=ActionType.OPEN, side=Side(side))


# ---------------------------------------------------------------------------
# The press is the bot's own order path
# ---------------------------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_manual_entry_becomes_the_bots_own_trade():
    """Same fan-out, same accounts, same row — stamped with the run.

    The stamp is the feature: a trade with no ``bot_run`` is a trade
    ``read_held`` will never find, and the strategy would go on evaluating as
    if the platform were flat.
    """
    await _account("bot-on", bot=True)
    await _account("bot-off", bot=False)
    bot = await _bot()
    run = await _open_run(bot)

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    assert outcome.ok and outcome.code == "routed"
    trade = (await _trades())[0]
    assert (trade.side, trade.status, trade.bot_run_id) == ("long", TradeStatus.OPEN, run.id)
    # §5's protection comes from the bot, not from a second set of numbers
    # typed into a dialog.
    assert (trade.sl_pct, trade.tp_pct) == (Decimal("1"), Decimal("2"))
    legs = await sync_to_async(
        lambda: [leg.account.label for leg in trade.legs.select_related("account")]
    )()
    assert legs == ["bot-on"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_action_records_that_a_person_did_it():
    await _account("bot-on", bot=True)
    bot = await _bot()
    await _open_run(bot)

    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    row = await sync_to_async(lambda: BotAction.objects.get())()
    assert row.action_type == ActionType.OPEN
    assert row.intent["origin"] == "manual"
    assert row.intent["actor"] == "boss"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bar_driven_action_still_serialises_without_the_new_fields(staged):
    """Every bot that predates Q41 keeps reading the same way.

    ``origin``/``actor`` are written only when a person is behind the action,
    so a bar's stored intent is byte-for-byte what it was before the fields
    existed.
    """
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)

    await _bars(run, bot, (1000, True))

    row = await sync_to_async(lambda: BotAction.objects.get())()
    assert "origin" not in row.intent and "actor" not in row.intent


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_entry_is_refused_while_the_bot_is_stopped():
    """Nothing would manage it. Said in front of the button, not after."""
    await _account("bot-on", bot=True)
    bot = await _bot(state=BotState.STOPPED)

    with pytest.raises(intervene.Refused) as refused:
        await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    assert refused.value.code == "bot_not_running"
    assert await _trades() == []


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_exit_is_allowed_on_a_stopped_bot_that_is_still_holding():
    """The case this tab is most needed for: a bot that stopped itself at 03:00
    while holding. Refusing to flatten it would be the panel protecting a rule
    at the operator's expense."""
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")
    await supervisor.stop(bot.id, reason="manual", detail="stopped", actor="boss")

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")

    assert outcome.ok and outcome.run_id == run.id
    assert (await _trades())[0].status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_opening_the_side_already_held_sends_nothing():
    await _account("bot-on", bot=True)
    bot = await _bot()
    await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    assert outcome.code == "already_there"
    assert len(await _trades()) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_closing_with_nothing_open_sends_nothing():
    await _account("bot-on", bot=True)
    bot = await _bot()
    await _open_run(bot)

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")

    assert outcome.code == "already_flat"
    assert await _trades() == []


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_opening_the_other_way_is_a_sequenced_reversal():
    """``plan()``'s own rule, reached from here unchanged: close, confirm flat,
    then open. Fired together at a venue that nets positions the result is a
    doubled position or a cancelled one."""
    await _account("bot-on", bot=True)
    bot = await _bot()
    await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.OPEN_SHORT, actor="boss")

    assert outcome.ok
    types = [action["action"]["type"] for action in outcome.actions]
    assert types == [ActionType.CLOSE, ActionType.OPEN]
    trades = await _trades()
    assert [(t.side, t.status) for t in trades] == [
        ("long", TradeStatus.CLOSED),
        ("short", TradeStatus.OPEN),
    ]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_halt_refuses_an_entry_and_still_allows_an_exit():
    """Q14, unchanged by this door. Closing while halted is a protection
    action; opening while halted is the thing the halt exists to stop."""
    await _account("bot-on", bot=True)
    bot = await _bot()
    await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")
    await sync_to_async(killswitch.set_stop_all)(True, actor="boss")

    with pytest.raises(intervene.Refused) as refused:
        await intervene.act(bot_id=bot.id, verb=intervene.OPEN_SHORT, actor="boss")
    assert refused.value.code == "halt"

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")
    assert outcome.ok
    assert (await _trades())[0].status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_paper_bot_records_the_press_and_routes_nothing():
    await _account("bot-on", bot=True)
    bot = await _bot(state=BotState.PAPER)
    await _open_run(bot)

    outcome = await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    assert outcome.code == "paper"
    assert await _trades() == []
    assert (await _actions())[0][0] == ActionType.SHADOW


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_two_presses_in_the_same_second_place_one_order(monkeypatch):
    """The idempotency key is the double-click guard, and it is a database
    constraint rather than application logic — the case it defends against is
    two requests in flight at once, and at that moment nothing is holding a
    lock."""
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)

    first = await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")
    # The second press, with the position deliberately not yet reconciled —
    # the same second, the same run, the same action type.
    await sync_to_async(
        lambda: Trade.objects.filter(bot_run=run).update(bot_run=None)
    )()
    second = await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    assert first.ok
    assert second.actions[0].get("skipped") == "already_dispatched"
    assert len(await _trades()) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_unknown_verb_is_refused_by_name():
    bot = await _bot()
    await _open_run(bot)

    with pytest.raises(intervene.Refused) as refused:
        await intervene.act(bot_id=bot.id, verb="liquidate_everything", actor="boss")

    assert refused.value.status == 400


# ---------------------------------------------------------------------------
# A hand-opened position is the bot's to manage
# ---------------------------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_strategys_own_exit_closes_what_the_operator_opened(staged):
    """The promise of the feature, end to end.

    Nothing teaches the strategy about the press. The trade is stamped with the
    run, ``read_held`` finds it, ``sync_position`` tells the runtime before the
    bar is evaluated, and the script's ``strategy.close`` does the rest.
    """
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    # One red bar: the script's exit condition.
    await _bars(run, bot, (1000, False))

    trade = (await _trades())[0]
    assert trade.status == TradeStatus.CLOSED
    closes = [row for row in await _actions() if row[0] == ActionType.CLOSE]
    assert closes and closes[-1][1] is True


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_quiet_bar_after_a_hand_opened_entry_does_not_close_it(staged):
    """The failure the position sync exists to prevent (Q38), reached from this
    door: a runtime that was never told what is held starts every bar flat, and
    the first quiet bar becomes an instruction to close."""
    await _account("bot-on", bot=True)
    bot = await _bot(
        source=(
            "//@version=5\n"
            'strategy("enter on green only", overlay=true)\n'
            "if close > open\n"
            '    strategy.entry("Long", strategy.long)\n'
        )
    )
    run = await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    await _bars(run, bot, (1000, False))

    assert (await _trades())[0].status == TradeStatus.OPEN


# ---------------------------------------------------------------------------
# A hand-closed position is not reopened behind the operator's back
# ---------------------------------------------------------------------------


def test_the_guard_holds_the_entry_the_press_overrode():
    assert (
        intervene.decide([_open()], guard_side="long", guard_bar=100, bar_time=200)
        == intervene.HOLD
    )


def test_the_guard_arms_when_the_script_stops_asking():
    assert (
        intervene.decide([], guard_side="long", guard_bar=100, bar_time=200)
        == intervene.ARM
    )


def test_an_armed_guard_releases_on_the_next_ask():
    assert (
        intervene.decide([_open()], guard_side="long", guard_bar=None, bar_time=300)
        == intervene.CLEAR
    )


def test_the_bar_the_press_landed_on_does_not_arm_the_guard():
    """Otherwise the very bar being overridden would release it, and the
    position would be back one bar later."""
    assert (
        intervene.decide([], guard_side="long", guard_bar=200, bar_time=200)
        == intervene.PASS
    )


def test_an_entry_the_other_way_retires_the_guard():
    assert (
        intervene.decide([_open("short")], guard_side="long", guard_bar=100, bar_time=200)
        == intervene.CLEAR
    )


@pytest.mark.parametrize(
    "action",
    [
        Action(type=ActionType.CLOSE),
        Action(type=ActionType.AMEND, side=Side.LONG),
        Action(type=ActionType.REDUCE, side=Side.LONG, fraction=Decimal("0.5")),
    ],
)
def test_the_guard_never_holds_off_anything_but_an_entry(action):
    """A close, an amend or a scale-out is not something the operator asked not
    to happen — and holding off a close would leave a position running that the
    strategy has decided to end."""
    assert (
        intervene.decide([action], guard_side="long", guard_bar=100, bar_time=200)
        != intervene.HOLD
    )


def test_no_guard_is_no_opinion():
    assert (
        intervene.decide([_open()], guard_side="", guard_bar=None, bar_time=200)
        == intervene.PASS
    )


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_hand_closed_side_is_not_re_entered_until_the_signal_comes_again(staged):
    """The whole rule, through the real loop, on a strategy whose entry
    condition is a *state*.

    Green bar in — closed by hand — green bar (still asking, held off) — red bar
    (the script stops asking) — green bar (a new signal, routed).
    """
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)

    await _bars(run, bot, (1000, True))
    assert len(await _trades()) == 1

    await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")
    run = await _reload(run)
    assert run.manual_flat_side == "long"

    # Still asking. Nothing is sent, and the refusal is written down.
    await _bars(run, bot, (1001, True))
    assert len(await _trades()) == 1
    assert (ActionType.SHADOW, True, "", True) in await _actions()

    # The script stops asking: from here the next ask is a new signal.
    run = await _reload(run)
    await _bars(run, bot, (1002, False))
    run = await _reload(run)
    assert run.manual_flat_side == "long" and run.manual_flat_bar is None

    # And it comes.
    await _bars(run, bot, (1003, True))
    trades = await _trades()
    assert len(trades) == 2 and trades[1].status == TradeStatus.OPEN
    run = await _reload(run)
    assert run.manual_flat_side == ""


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_hand_opened_position_clears_the_guard():
    """The operator has put the position back on themselves. There is nothing
    left to protect from being re-entered."""
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")
    await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")
    assert (await _reload(run)).manual_flat_side == "long"

    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    assert (await _reload(run)).manual_flat_side == ""


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_guard_does_not_outlive_its_run():
    """A stop and a start is a new run, and a new run has no history to hold
    off. The operator restarting the bot is the operator saying so."""
    await _account("bot-on", bot=True)
    bot = await _bot()
    run = await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")
    await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")
    await supervisor.stop(bot.id, reason="manual", detail="", actor="boss")

    fresh = await _open_run(bot)

    assert fresh.id != run.id
    assert fresh.manual_flat_side == "" and fresh.manual_flat_bar is None


# ---------------------------------------------------------------------------
# What the operator is shown before pressing anything
# ---------------------------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_desk_names_the_divergence_the_operator_came_to_fix(staged):
    """The tab's one question. A strategy that wants in while the platform
    holds nothing is not "aligned with no position" — it is the difference the
    operator is looking at on TradingView."""
    await _account("bot-off", bot=False)  # nothing can be routed to
    bot = await _bot()
    run = await _open_run(bot)

    await _bars(run, bot, (1000, True))

    payload = await sync_to_async(desk.payload)(bot, user=_user())
    assert payload["divergence"]["code"] == desk.STRATEGY_WANTS_IN
    assert payload["divergence"]["wants"] == "long"
    assert payload["strategy"]["entry_signal"] is True
    assert payload["capital"]["eligible"] == 0


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_desk_reports_the_position_and_the_money_behind_it():
    await _account("bot-on", bot=True, balance="1000")
    bot = await _bot()
    await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")

    payload = await sync_to_async(desk.payload)(bot, user=_user())

    assert payload["position"]["trade"]["side"] == "long"
    assert payload["position"]["totals"]["accounts"] == 1
    assert payload["capital"]["eligible"] == 1
    assert payload["capital"]["available"] is not None
    assert payload["divergence"]["holds"] == "long"
    assert payload["can"]["close"] is True


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_desk_says_what_is_being_held_off():
    await _account("bot-on", bot=True)
    bot = await _bot()
    await _open_run(bot)
    await intervene.act(bot_id=bot.id, verb=intervene.OPEN_LONG, actor="boss")
    await intervene.act(bot_id=bot.id, verb=intervene.CLOSE, actor="boss")

    payload = await sync_to_async(desk.payload)(bot, user=_user())

    assert payload["hold_off"]["side"] == "long"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bot_that_has_never_run_is_unknown_rather_than_aligned():
    """"Nothing to compare" and "they agree" are different answers, and only
    the second one is a reason to do nothing."""
    bot = await _bot(state=BotState.DRAFT)

    payload = await sync_to_async(desk.payload)(bot, user=_user())

    assert payload["divergence"]["code"] == desk.UNKNOWN
    assert payload["can"] == {"open": False, "close": False, "code": "bot_not_running"}


def _user():
    return User(username="boss", is_staff=True)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_endpoints_are_staff_only():
    bot = make_bot(source=SOURCE)
    anonymous = Client()
    assert anonymous.get(f"/api/bots/bots/{bot.id}/desk/").status_code in (401, 403)
    assert anonymous.post(
        f"/api/bots/bots/{bot.id}/intervene/",
        data=json.dumps({"verb": "close"}),
        content_type="application/json",
    ).status_code in (401, 403)


@pytest.mark.django_db
def test_the_endpoint_answers_with_the_reason_a_press_was_refused():
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    bot = make_bot(source=SOURCE, state=BotState.STOPPED)

    response = client.post(
        f"/api/bots/bots/{bot.id}/intervene/",
        data=json.dumps({"verb": "open_long"}),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "bot_not_running"
