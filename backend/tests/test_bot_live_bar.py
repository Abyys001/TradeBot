"""One live bar, driven through the supervisor's own loop against the database.

The bar loop was covered from every side except the one that runs: the state
machine, the translator, the risk gate and the routing layer each had their own
tests, and `_run_bot` — the function that calls all four, bar after bar, on a
live book — had none that reached the database.

That is how `_current_equity` shipped asking `ConnectedAccount` for a field
called `active`. It has never had one. Every live run raised `FieldError` on
its **first** bar, `_supervise_inner` caught it as the catch-all, and the bot
stopped itself with `script_error` — naming the operator's strategy for a fault
that was in this module. A bot started overnight was stopped by the time
anybody looked.

So these do not mock the loop's database calls: two accounts, one with the bot
switch on, a green bar, and the trade that comes out the far end. Only the two
things a test cannot have are replaced — the feed (a fixed script of bars
instead of an exchange's clock) and the public ticker.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.bots import supervisor
from apps.bots.feed import FeedBar
from apps.bots.models import BotState
from apps.pine.bar import Bar
from apps.trading.models import Trade
from tests.bot_factory import make_bot

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

KEY = Fernet.generate_key().decode()

#: Enters on any bar that closed above its open — so the bar the feed yields
#: decides whether the loop routes, and the test decides the bar.
SOURCE = """//@version=5
strategy("green bar", overlay=true)
if close > open
    strategy.entry("Long", strategy.long)
"""

STEP = 1800  # 30m, matching the bot below
FIRST = 1_700_000_000


def _bar(index: int, *, green: bool) -> Bar:
    open_ = Decimal("100")
    close = Decimal("101") if green else Decimal("99")
    return Bar(
        time=FIRST + index * STEP,
        open=open_,
        high=max(open_, close),
        low=min(open_, close),
        close=close,
        volume=Decimal("10"),
    )


class ScriptedFeed:
    """`BarFeed`'s shape, with the exchange's clock replaced by a list.

    Warm-up is every bar red, so nothing the loop discards would have traded
    anyway; the one live bar is green, which is the signal.
    """

    def __init__(self, *, symbol: str, interval: str, market, **_: object) -> None:
        self.symbol = symbol
        self.interval = interval
        self.market = market
        self.transport = "poll"
        self.source = "scripted"
        self.gaps = 0
        self.gaps_repaired = 0
        #: The newest bar the feed has seen, which the risk gate measures
        #: staleness against. A scripted feed has no clock to be stale by, so
        #: it reports none and the gate abstains rather than guessing.
        self.last_bar_time = None

    async def check_clock(self) -> None:
        return None

    async def warmup(self, *, lookback: int | None = None, bars: int | None = None) -> list[Bar]:
        return [_bar(i, green=False) for i in range((bars if bars is not None else lookback) + 10)]

    async def __aiter__(self):
        yield FeedBar(bar=_bar(1_000, green=True), source="scripted", transport="poll")


@sync_to_async
def _account(label: str, *, bot: bool, balance: str = "1000", status=AccountStatus.ACTIVE):
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=status,
        withdrawal_check_passed=True,
        bot_trading_enabled=bot,
        last_balance=Decimal(balance),
        last_balance_asset="USDT",
    )


@pytest.fixture
def live_loop(monkeypatch):
    """The loop with its two outside dependencies pinned, and nothing else."""
    from apps.exchanges import marketdata

    monkeypatch.setattr(supervisor, "BarFeed", ScriptedFeed)
    monkeypatch.setattr(
        marketdata,
        "get_ticker",
        lambda **_: {"price": "101", "live": True, "source": "test"},
    )


async def _run_one_bar(bot) -> None:
    run = await supervisor._open_run(bot, actor="tester")
    await supervisor._run_bot(bot.id, run.id)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_live_bar_opens_a_position_on_the_opted_in_account(live_loop):
    """The whole point of the feature, end to end: signal in, legs out.

    `FieldError` is not caught anywhere between `_run_state` and the caller, so
    a per-bar query naming a field that does not exist fails this test with the
    exchange's own words rather than as `script_error` at three in the morning.
    """
    await _account("bot-on", bot=True)
    await _account("bot-off", bot=False)
    bot = await sync_to_async(make_bot)(
        source=SOURCE,
        state=BotState.LIVE,
        symbol="BTCUSDT",
        interval="30m",
        sl_pct="1",
        tp_pct="2",
    )

    await _run_one_bar(bot)

    legs = await sync_to_async(
        lambda: [
            (leg.account.label, leg.ok)
            for leg in Trade.objects.get().legs.select_related("account")
        ]
    )()
    assert legs == [("bot-on", True)]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_no_account_opted_in_is_a_bar_that_sits_out_not_a_dead_bot(live_loop):
    """Q22: "sat out", not a failure. The bot goes on evaluating bars.

    An account is switched on mid-run more often than a bot is restarted, so
    the loop that finds nobody opted in has to survive to see it happen.
    """
    await _account("bot-off", bot=False)
    bot = await sync_to_async(make_bot)(
        source=SOURCE,
        state=BotState.LIVE,
        symbol="BTCUSDT",
        interval="30m",
        sl_pct="1",
        tp_pct="2",
    )

    await _run_one_bar(bot)

    assert await Trade.objects.acount() == 0
    assert await sync_to_async(lambda: supervisor._load_bot(bot.id).state)() == BotState.LIVE


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_equity_the_script_reads_is_the_live_accounts(live_loop):
    """`strategy.equity`, on every bar, from `status` — the field that exists.

    Deliberately the same set as `riskgate._run_equity`: the book a drawdown
    limit measures and the book the script reads are one book. The bot switch
    is not in it — it says who takes an *entry*, not whose money is on the
    platform — and a paused account's balance is still on the platform.
    """
    await _account("bot-on", bot=True, balance="1000")
    await _account("bot-off", bot=False, balance="500")
    await _account("errored", bot=True, balance="4000", status=AccountStatus.ERROR)

    assert await sync_to_async(supervisor._current_equity)() == Decimal("1500")


# --- the protection a bot must be able to send ------------------------------

#: The shape of the script this was found on: entries from the engine, exits
#: managed by the script itself on later bars with `strategy.close`. Nothing in
#: it ever hands the platform a percentage.
NO_EXIT_SOURCE = SOURCE

#: The other half of Q21 — the script sets both, so the bot's own pair may be
#: blank and every entry still carries protection.
SCRIPT_EXIT_SOURCE = """//@version=5
strategy("green bar with its own exit", overlay=true)
if close > open
    strategy.entry("Long", strategy.long)
strategy.exit("X", "Long", loss_pct=1, profit_pct=2)
"""


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_live_bot_that_could_never_send_a_protected_order_refuses_to_start(live_loop):
    """Both halves are mandatory (§4/§5), so a bot missing them cannot trade.

    Before this, it started, evaluated bars, planned the entry and had it
    refused inside `route_open` — once per signal, forever, while the panel
    showed a healthy running bot. The refusal belongs in front of the person
    pressing start.
    """
    await _account("bot-on", bot=True)
    bot = await sync_to_async(make_bot)(
        source=NO_EXIT_SOURCE, state=BotState.LIVE, symbol="BTCUSDT", interval="30m"
    )

    with pytest.raises(supervisor._AutoStop) as caught:
        await _run_one_bar(bot)

    assert "stop loss" in caught.value.detail and "take profit" in caught.value.detail
    assert await Trade.objects.acount() == 0


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_only_the_missing_half_is_named(live_loop):
    await _account("bot-on", bot=True)
    bot = await sync_to_async(make_bot)(
        source=NO_EXIT_SOURCE,
        state=BotState.LIVE,
        symbol="BTCUSDT",
        interval="30m",
        sl_pct="1",
    )

    with pytest.raises(supervisor._AutoStop) as caught:
        await _run_one_bar(bot)

    assert "take profit" in caught.value.detail
    assert "stop loss" not in caught.value.detail


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_script_that_sets_its_own_percentages_needs_no_bot_pair(live_loop):
    """Q21: a percent `strategy.exit` wins, and the bot's pair is the fallback."""
    await _account("bot-on", bot=True)
    bot = await sync_to_async(make_bot)(
        source=SCRIPT_EXIT_SOURCE, state=BotState.LIVE, symbol="BTCUSDT", interval="30m"
    )

    await _run_one_bar(bot)

    trade = await sync_to_async(Trade.objects.get)()
    assert (trade.sl_pct, trade.tp_pct) == (Decimal("1"), Decimal("2"))


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_paper_still_runs_and_says_what_live_would_refuse(live_loop, caplog):
    """Shadow mode routes nothing, so it is allowed to run — and it is the last
    place the gap can be noticed before promotion, so it is said out loud."""
    await _account("bot-on", bot=True)
    bot = await sync_to_async(make_bot)(
        source=NO_EXIT_SOURCE, state=BotState.PAPER, symbol="BTCUSDT", interval="30m"
    )

    with caplog.at_level("WARNING"):
        await _run_one_bar(bot)

    codes = [getattr(record, "error_code", "") for record in caplog.records]
    assert "bot_unprotected" in codes
    assert await Trade.objects.acount() == 0
