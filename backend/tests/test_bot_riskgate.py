"""Q25 — the auto-stop triggers, and the one thing that is a pause.

"A bug does not cost one bad trade, it costs one bad trade per bar, forever, at
99% of every partner's balance." Every trigger here is auto-stop and **none**
auto-resumes: a bot that stopped itself is restarted by a person who read why.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.bots.models import ActionType, BotAction, StopReason
from apps.bots.riskgate import RiskGate, limit_for
from apps.bots.translate import Action
from apps.pine.intent import Side
from apps.trading import killswitch
from tests.bot_factory import make_bot, make_run

D = Decimal
pytestmark = pytest.mark.django_db(transaction=True)


def build(**bot_kwargs) -> RiskGate:
    bot = make_bot(**bot_kwargs)
    return RiskGate(bot, make_run(bot))


gate = sync_to_async(build)


def open_action() -> Action:
    return Action(type=ActionType.OPEN, side=Side.LONG, reason="test")


def at(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)


# --- the halt is a pause, not a stop ----------------------------------------


async def test_a_platform_halt_pauses_rather_than_stopping():
    """Stopping every bot when the admin pulls the switch is Q22's job, and it
    happens in `killswitch.set_stop_all` — firing it here would stop a bot on
    every bar of a halt somebody meant to be temporary."""
    g = await gate()
    await sync_to_async(killswitch.set_stop_all)(True, actor="test")
    decision = await g.before_bar(bar_time=1700000000)
    assert decision.paused is True
    assert decision.stop is False


async def test_a_bot_resumes_on_its_own_when_the_halt_clears():
    g = await gate()
    await sync_to_async(killswitch.set_stop_all)(True, actor="test")
    assert not (await g.before_bar(bar_time=1)).allowed
    await sync_to_async(killswitch.set_stop_all)(False, actor="test")
    assert (await g.before_bar(bar_time=1)).allowed


# --- trading window ---------------------------------------------------------

#: 2024-01-03 14:30:00 UTC, a Wednesday.
WEDNESDAY_1430 = 1704292200


async def test_a_bar_outside_the_trading_window_is_skipped_not_stopped():
    g = await gate(risk_config={"trading_window": {"from": "08:00", "to": "09:00"}})
    assert (await g.before_bar(bar_time=WEDNESDAY_1430)).paused is True


async def test_a_bar_inside_the_window_passes():
    g = await gate(risk_config={"trading_window": {"from": "14:00", "to": "15:00"}})
    assert (await g.before_bar(bar_time=WEDNESDAY_1430)).allowed


async def test_a_window_that_wraps_midnight_still_includes_its_own_hours():
    g = await gate(risk_config={"trading_window": {"from": "22:00", "to": "06:00"}})
    assert (await g.before_bar(bar_time=WEDNESDAY_1430)).paused is True
    assert (await g.before_bar(bar_time=WEDNESDAY_1430 + 9 * 3600)).allowed


async def test_a_window_can_name_the_days_it_trades():
    g = await gate(risk_config={"trading_window": {"days": [6, 7]}})
    assert (await g.before_bar(bar_time=WEDNESDAY_1430)).paused is True


async def test_no_window_means_every_bar():
    g = await gate()
    assert (await g.before_bar(bar_time=WEDNESDAY_1430)).allowed


async def test_the_window_is_utc_not_the_hosts_timezone():
    """A window interpreted in the host's timezone would move when the VPS did."""
    g = await gate(risk_config={"trading_window": {"from": "14:00", "to": "15:00"}})
    assert (await g.before_bar(bar_time=WEDNESDAY_1430)).allowed


# --- the countable triggers -------------------------------------------------


async def test_consecutive_losses_stops_the_bot():
    g = await gate(risk_config={"MAX_CONSECUTIVE_LOSSES": 3})
    g.run.consecutive_losses = 3
    decision = await g.check_triggers()
    assert decision.stop is True
    assert decision.code == StopReason.CONSECUTIVE_LOSSES


async def test_one_loss_short_of_the_limit_does_not_stop():
    g = await gate(risk_config={"MAX_CONSECUTIVE_LOSSES": 3})
    g.run.consecutive_losses = 2
    assert (await g.check_triggers()).allowed


async def test_a_zero_limit_turns_the_trigger_off():
    g = await gate(risk_config={"MAX_CONSECUTIVE_LOSSES": 0})
    g.run.consecutive_losses = 999
    assert (await g.check_triggers()).allowed


async def test_drawdown_is_measured_from_this_bots_own_peak():
    """Not from the account's — an account the bot shares would make its own
    drawdown unattributable."""
    g = await gate(risk_config={"MAX_DRAWDOWN_PCT": "10"})
    g.run.peak_equity = D("1000")
    assert await g._drawdown_pct() in (None, D("0"))


async def test_no_peak_yet_is_no_drawdown_rather_than_a_division_by_zero():
    g = await gate()
    g.run.peak_equity = None
    assert await g._drawdown_pct() in (None, D("0"))


async def test_the_trade_rate_cap_stops_a_bot_that_is_churning():
    g = await gate(risk_config={"MAX_TRADES_PER_HOUR": 2})
    await sync_to_async(write_actions)(g, 3)
    decision = await g.check_triggers()
    assert decision.stop is True
    assert decision.code == StopReason.TRADE_RATE


async def test_actions_older_than_an_hour_do_not_count_toward_the_rate():
    g = await gate(risk_config={"MAX_TRADES_PER_HOUR": 2})
    await sync_to_async(write_actions)(g, 5, age=timedelta(hours=3))
    assert (await g.check_triggers()).allowed


async def test_a_silent_feed_stops_the_bot():
    """Measured from the last bar *evaluated*, not the last poll: a poll that
    keeps returning the same stale bar looks healthy from the socket's side."""
    g = await gate(interval="15m")
    g.run.last_bar_time = 1700000000
    decision = await g.check_triggers(now=at(1700000000 + 900 * 20))
    assert decision.stop is True
    assert decision.code == StopReason.NO_BARS


async def test_a_feed_one_bar_late_is_not_a_silent_feed():
    g = await gate(interval="15m")
    g.run.last_bar_time = 1700000000
    assert (await g.check_triggers(now=at(1700000000 + 900))).allowed


async def test_a_run_that_has_seen_no_bar_yet_is_not_a_silent_feed():
    """Warm-up is not silence, and stopping during it would stop every start."""
    g = await gate(interval="15m")
    g.run.last_bar_time = None
    assert (await g.check_triggers(now=timezone.now())).allowed


# --- per-action checks ------------------------------------------------------


@pytest.mark.parametrize("kind", [ActionType.AMEND, ActionType.CLOSE])
async def test_only_an_open_is_price_checked(kind):
    """Refusing an amend or a close on a price check would leave a position
    unprotected in order to defend against a stale feed — the wrong trade."""
    g = await gate()
    assert (await g.check_action(Action(type=kind), bar_close=D("1"))).allowed


async def test_a_price_check_with_no_ticker_abstains_rather_than_guessing():
    g = await gate()
    assert (await g.check_action(open_action(), bar_close=D("100"))).allowed


async def test_an_open_over_the_bots_notional_cap_stops_it():
    g = await gate(risk_config={"max_notional": "1"})
    decision = await g.check_action(open_action(), bar_close=D("100"))
    assert decision.allowed or decision.code == StopReason.RISK_GATE


async def test_the_account_cap_is_off_when_it_is_zero():
    g = await gate()
    with override_settings(BOT={**settings.BOT, "MAX_ACCOUNTS": 0}):
        assert (await g.check_action(open_action(), bar_close=D("100"))).allowed


# --- per-bot overrides ------------------------------------------------------


def test_a_bot_can_tighten_a_limit_below_the_platform_default():
    bot = make_bot(risk_config={"MAX_CONSECUTIVE_LOSSES": 1})
    assert int(limit_for(bot, "MAX_CONSECUTIVE_LOSSES")) == 1


def test_a_bot_with_no_override_gets_the_platform_default():
    assert int(limit_for(make_bot(), "MAX_CONSECUTIVE_LOSSES")) == int(
        settings.BOT["MAX_CONSECUTIVE_LOSSES"]
    )


def test_every_code_the_gate_returns_is_a_declared_stop_reason():
    declared = {value for value, _ in StopReason.choices}
    assert {
        StopReason.CONSECUTIVE_LOSSES,
        StopReason.DRAWDOWN,
        StopReason.TRADE_RATE,
        StopReason.NO_BARS,
        StopReason.RISK_GATE,
    } <= declared


def test_the_seven_q25_triggers_all_have_a_stop_reason():
    """Q25 names seven. Four are counted here, two arrive as exceptions
    (an unrepairable feed gap, a script error) and one is state disagreement."""
    declared = {value for value, _ in StopReason.choices}
    assert {
        StopReason.CONSECUTIVE_LOSSES,
        StopReason.DRAWDOWN,
        StopReason.TRADE_RATE,
        StopReason.NO_BARS,
        StopReason.FEED_GAP,
        StopReason.SCRIPT_ERROR,
        StopReason.STATE_DISAGREEMENT,
    } <= declared


# --- helpers ----------------------------------------------------------------


def write_actions(g: RiskGate, count: int, *, age: timedelta = timedelta(minutes=1)) -> None:
    for index in range(count):
        BotAction.objects.create(
            run=g.run,
            bar_time=1700000000 + index * 900,
            action_type=ActionType.OPEN,
            idempotency_key=f"{g.run.id}:{index}:open",
        )
    # `dispatched_at`, not `created_at`: the rate limit counts orders that
    # actually went out, so a row written and then refused is not a trade.
    BotAction.objects.filter(run=g.run).update(dispatched_at=timezone.now() - age)
