"""The platform's own exit, driven through the supervisor's loop to a closed trade.

``test_bot_exit_guard.py`` covers the decision — which bar reaches which level.
This covers the consequence: that the decision becomes a real ``CLOSE`` on the
one order path, reaching every account that took the entry, recorded as a
``BotAction`` like anything else, and that it does not fire on a bar that did
not reach anything.

It reuses the scripted feed from ``test_bot_live_bar.py`` rather than building a
second one — the point is that this rides the loop everything else rides.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings

from apps.bots import supervisor
from apps.bots.feed import FeedBar
from apps.bots.models import ActionType, BotAction, BotState
from apps.pine.bar import Bar
from apps.trading.models import Trade, TradeStatus
from tests.bot_factory import make_bot
from tests.test_bot_live_bar import KEY, STEP, ScriptedFeed, _account

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

#: Enters on the first green bar and then says nothing ever again — the shape
#: of a strategy whose exits are meant to come from levels resting at the
#: venue. If those levels are not there, nothing in the script will close it.
#: The paper adapter's mark for BTCUSDT, which is what it fills at and so what
#: the trade records as its entry. The bars have to be in the same world as the
#: fills: the guard resolves its levels off ``Trade.admin_entry_price`` and
#: compares them against the feed's bar, and a test whose feed quotes 101 while
#: its exchange quotes 100,000 is testing a symbol mapped to the wrong
#: instrument — which is the risk gate's price-drift check, not this.
MARK = Decimal("100000")

SOURCE = """//@version=5
strategy("enter once", overlay=true)
var bool taken = false
if close > open and not taken
    taken := true
    strategy.entry("Long", strategy.long)
"""


#: Same shape, but with an exit the supervisor can see. A strategy-managed bot
#: whose script can never close anything is refused at the button by
#: `protection_gap`, which is a different guard with its own tests — this one
#: needs a bot that starts and a trade with no level recorded.
CAN_EXIT_SOURCE = """//@version=5
strategy("enter once, exit never in this window", overlay=true)
var bool taken = false
if close > open and not taken
    taken := true
    strategy.entry("Long", strategy.long)
if taken and close < open * 0.5
    strategy.close("Long")
"""


class _TwoBarFeed(ScriptedFeed):
    """One green bar to enter on, then one bar whose range is the test's.

    The two bars are stamped at *now*, unlike the warm-up's, because the risk
    gate's `no_bars` auto-stop measures the newest bar against the wall clock
    (Q25) and a bar from 2023 is a feed it would rightly stop the bot over.
    """

    #: Set per test: the high and low of the second bar.
    second: tuple[str, str] = ("101", "99")
    #: The close of the bar last handed over. The patched ticker reads it, so
    #: the risk gate's bar-versus-ticker drift check sees a feed that agrees
    #: with the market — which is what it is there to measure, and not what
    #: these tests are about.
    latest: Decimal = MARK

    async def __aiter__(self):
        now = (int(time.time()) // STEP) * STEP
        entry = Bar(
            time=now - STEP,
            open=MARK - Decimal("100"),
            high=MARK,
            low=MARK - Decimal("100"),
            close=MARK,
            volume=Decimal("10"),
        )
        self.last_bar_time = entry.time
        type(self).latest = entry.close
        yield FeedBar(bar=entry, source="scripted", transport="poll")
        high, low = self.second
        self.last_bar_time = now
        type(self).latest = Decimal(high)
        yield FeedBar(
            bar=Bar(
                time=now,
                open=entry.close,
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(high),
                volume=Decimal("10"),
            ),
            source="scripted",
            transport="poll",
        )


@pytest.fixture
def two_bars(monkeypatch):
    from apps.exchanges import marketdata

    monkeypatch.setattr(supervisor, "BarFeed", _TwoBarFeed)
    monkeypatch.setattr(
        marketdata,
        "get_ticker",
        lambda **_: {"price": str(_TwoBarFeed.latest), "live": True, "source": "test"},
    )
    return _TwoBarFeed


async def _bot(**kwargs):
    return await sync_to_async(make_bot)(
        source=SOURCE,
        state=BotState.LIVE,
        symbol="BTCUSDT",
        interval="30m",
        **kwargs,
    )


async def _run(bot):
    run = await supervisor._open_run(bot, actor="tester")
    await supervisor._run_bot(bot.id, run.id)


@sync_to_async
def _trades():
    return list(Trade.objects.order_by("id"))


@sync_to_async
def _actions():
    return [(row.action_type, row.reason, row.ok) for row in BotAction.objects.order_by("id")]


@sync_to_async
def _legs(trade):
    return sorted(leg.account.label for leg in trade.legs.select_related("account"))


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bar_that_reached_the_stop_closes_the_trade_the_script_never_would(
    two_bars,
):
    """The failure this exists for, end to end.

    The entry fills at the mark with a 1% stop, so the level is 1% below it.
    The next bar trades 2% down — and the script has nothing more to say.
    Before the guard, the position stayed open until a human noticed.
    """
    two_bars.second = (str(MARK), str(MARK * Decimal("0.98")))
    await _account("partner-a", bot=True)
    bot = await _bot(sl_pct="1", tp_pct="20")

    await _run(bot)

    trade = (await _trades())[0]
    assert trade.status == TradeStatus.CLOSED
    assert (ActionType.CLOSE, "exit signal: stop", True) in await _actions()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_close_reaches_every_account_that_took_the_entry(two_bars):
    """§4: an exit fans out exactly as the entry did, or one partner is left holding."""
    two_bars.second = (str(MARK), str(MARK * Decimal("0.98")))
    await _account("partner-a", bot=True)
    await _account("partner-b", bot=True)
    await _account("not-opted-in", bot=False)
    bot = await _bot(sl_pct="1", tp_pct="20")

    await _run(bot)

    trade = (await _trades())[0]
    assert trade.status == TradeStatus.CLOSED
    assert await _legs(trade) == ["partner-a", "partner-b"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bar_that_reached_the_target_closes_it_too(two_bars):
    two_bars.second = (str(MARK * Decimal("1.12")), str(MARK))
    await _account("partner-a", bot=True)
    bot = await _bot(sl_pct="20", tp_pct="10")

    await _run(bot)

    assert (await _trades())[0].status == TradeStatus.CLOSED
    assert (ActionType.CLOSE, "exit signal: target", True) in await _actions()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_quiet_bar_leaves_the_position_exactly_where_it_was(two_bars):
    """The guard must be invisible on every bar that reached nothing.

    This is the half that is easy to lose: a level comparison that is slightly
    wrong in this direction closes live positions for no reason, which is worse
    than the bug it was written to fix.
    """
    two_bars.second = (str(MARK * Decimal("1.005")), str(MARK * Decimal("0.995")))
    await _account("partner-a", bot=True)
    bot = await _bot(sl_pct="20", tp_pct="20")

    await _run(bot)

    assert (await _trades())[0].status == TradeStatus.OPEN
    assert not [row for row in await _actions() if row[0] == ActionType.CLOSE]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_trade_with_no_level_recorded_is_left_alone(two_bars):
    """Q37's accepted exposure. Nothing rests at the venue and nothing is invented."""
    two_bars.second = (str(MARK), str(MARK * Decimal("0.5")))
    await _account("partner-a", bot=True)
    bot = await sync_to_async(make_bot)(
        source=CAN_EXIT_SOURCE,
        state=BotState.LIVE,
        symbol="BTCUSDT",
        interval="30m",
        exit_policy="strategy_managed",
    )

    await _run(bot)

    assert (await _trades())[0].status == TradeStatus.OPEN
