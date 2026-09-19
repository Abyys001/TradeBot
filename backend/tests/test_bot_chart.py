"""The chart tab — a visual backtest of real history, not a log of the bot's uptime.

The bug this file pins: the chart used to be built from ``BotBar``, the rows the
running bot recorded, so a bot started this morning had a chart that began this
morning. The operator's actual question — "would this have traded last night,
and did it?" — could not be asked of it. Every test here is a way of asking it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.bots import chart
from apps.bots.models import ActionType, BotAction
from apps.exchanges.feed_base import Candle
from tests import pine_corpus
from tests.bot_factory import make_bot, make_run

pytestmark = pytest.mark.django_db

D = Decimal
CROSS = (pine_corpus.ACCEPT / "01_sma_cross.pine").read_text()
STEP = 900  # 15m, the factory's default interval

#: A cross with the two things a published strategy has and `01_sma_cross`
#: does not: a `plotshape` whose series is a **condition**, and an exit that
#: happens in two parts under two names.
SHAPED = """//@version=5
strategy("Shaped cross", overlay=true, pyramiding=1)
fast = ta.sma(close, 9)
slow = ta.sma(close, 21)
up = ta.crossover(fast, slow)
down = ta.crossunder(fast, slow)
var bool banked = false
if up
    strategy.entry("Long", strategy.long, comment="Long")
    banked := false
if strategy.position_size > 0 and not banked and close > strategy.position_avg_price * 1.03
    strategy.close("Long", qty_percent=40, comment="Long TP1")
    banked := true
if down
    strategy.close("Long", comment="Long Exit")
plot(fast, title="Fast")
plotshape(up, title="Buy mark", style=shape.labelup, location=location.belowbar, text="BUY")
"""


def seed(stored: dict, *, bars: int, end: int) -> list[int]:
    """A saw-tooth series dense enough to cross a 9/21 SMA pair repeatedly.

    Deliberately not a random walk: a chart test that sometimes produced no
    trades would be a chart test that sometimes proved nothing.
    """
    times = [end - (bars - 1 - i) * STEP for i in range(bars)]
    for index, time in enumerate(times):
        # 40-bar triangle: up for twenty, down for twenty. Slow enough that the
        # slow average actually follows, so both crossings happen.
        leg = index % 40
        level = 100 + (leg if leg < 20 else 40 - leg)
        price = D(level)
        stored[time] = Candle(
            time=time,
            open=price,
            high=price + D("0.5"),
            low=price - D("0.5"),
            close=price,
            volume=D("1"),
        )
    return times


@pytest.fixture
def offline(monkeypatch):
    """The venue serves nothing beyond the archive. No test here reaches a network.

    Not only hygiene: "the archive ends here" is the case the scrollback has to
    handle, and a test that silently downloaded a thousand real bars would be
    testing Binance's uptime instead.
    """
    monkeypatch.setattr("apps.exchanges.feed_base.fetch_candles", lambda *a, **k: [])


@pytest.fixture
def bot_with_history(archive, offline):
    """A bot that has never been started, over a venue with months of bars."""
    bot = make_bot(source=CROSS, symbol="BTCUSDT", interval="15m")
    times = seed(archive, bars=1200, end=1_700_000_000 - (1_700_000_000 % STEP))
    return bot, times


def payload(bot, **kwargs):
    return chart.payload(bot, interval="15m", limit=kwargs.pop("limit", 300), **kwargs)


# --- history the bot never ran through --------------------------------------


def test_a_bot_that_has_never_run_still_has_a_chart_with_trades(bot_with_history, monkeypatch):
    """The whole point. No `BotRun`, no `BotBar`, and still a visual backtest."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot)

    assert bot.runs.count() == 0
    assert out["note"] == ""
    assert len(out["candles"]) > 200
    assert out["trades"], "the replay found no trades to draw"
    kinds = {marker["kind"] for marker in out["markers"]}
    assert {"entry", "exit"} <= kinds


def test_every_entry_marker_carries_the_price_the_fill_model_used(bot_with_history, monkeypatch):
    """A marker at a price nobody filled at is a marker that cannot be checked."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot)
    entries = [m for m in out["markers"] if m["kind"] == "entry"]
    by_time = {trade["entry_time"]: trade["entry_price"] for trade in out["trades"]}
    assert entries
    for marker in entries:
        assert marker["price"] == by_time[marker["time"]]


def test_the_plotted_series_come_from_the_same_replay_as_the_marks(bot_with_history, monkeypatch):
    """Two replays of one window is two opinions about where a trade happened."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot)
    names = {row["name"] for row in out["series"]}
    assert names, "the script plots two lines and neither was drawn"
    for row in out["series"]:
        assert row["points"], f"{row['name']} has no points"


# --- the script's own drawing ------------------------------------------------


def test_a_condition_is_never_drawn_on_the_price_scale(archive, offline, monkeypatch):
    """The bug that made the chart unrecognisable next to TradingView.

    ``plotshape(up)`` records ``False`` on every quiet bar. ``float(False)`` is
    0.0, so the series drew a flat line along the bottom, the price scale
    stretched to include it, and a thousand-dollar instrument was rendered as a
    two-pixel ribbon above zero.
    """
    bot = make_bot(source=SHAPED, symbol="BTCUSDT", interval="15m")
    times = seed(archive, bars=600, end=1_700_000_000 - (1_700_000_000 % STEP))
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot)
    assert [row["name"] for row in out["series"]] == ["Fast"]
    for row in out["series"]:
        for point in row["points"]:
            assert point["value"] > 1, "a condition reached the price scale"


def test_a_plotshape_is_a_mark_where_the_author_put_it(archive, offline, monkeypatch):
    bot = make_bot(source=SHAPED, symbol="BTCUSDT", interval="15m")
    times = seed(archive, bars=600, end=1_700_000_000 - (1_700_000_000 % STEP))
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    shapes = [m for m in payload(bot)["markers"] if m["kind"] == "shape"]
    assert shapes, "the script draws a label on every crossover and none was carried"
    for mark in shapes:
        assert mark["title"] == "Buy mark"
        assert mark["style"] == "shape.labelup"
        assert mark["location"] == "location.belowbar"
        assert mark["label"] == "BUY"


def test_a_scale_out_draws_one_entry_and_two_named_exits(archive, offline, monkeypatch):
    """TradingView's List of Trades is rows; its chart is campaigns.

    ``Long TP1`` and ``Long Exit`` share an entry bar and an entry price, and
    drawing a row at a time stacked two arrows under one candle — two entries
    the strategy never made.
    """
    bot = make_bot(source=SHAPED, symbol="BTCUSDT", interval="15m")
    times = seed(archive, bars=600, end=1_700_000_000 - (1_700_000_000 % STEP))
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot)
    entries = [m for m in out["markers"] if m["kind"] == "entry"]
    exits = [m for m in out["markers"] if m["kind"] == "exit"]
    assert len(entries) == len({(m["time"], m["price"]) for m in entries})
    assert len(exits) > len(entries), "the scale-out produced no second exit"
    assert {m["label"] for m in entries} == {"Long"}
    assert {"Long TP1", "Long Exit"} <= {m["label"] for m in exits}


# --- paging backwards -------------------------------------------------------


def test_paging_back_returns_the_window_before_the_one_on_screen(bot_with_history, monkeypatch):
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    first = payload(bot, limit=200)
    oldest = first["candles"][0]["time"]
    older = payload(bot, limit=200, before=oldest)

    assert older["candles"], "dragging back found nothing"
    assert max(bar["time"] for bar in older["candles"]) < oldest
    assert older["series"]


def test_two_pages_agree_about_the_bar_they_share(bot_with_history, monkeypatch):
    """One replay, sliced — the fix this module's docstring is about.

    A page-sized replay starts flat on its own left edge, so the same bar had
    one set of trades when it was in the middle of a page and another when it
    was near the start of one. The operator dragging the chart watched the
    marks move.
    """
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    wide = payload(bot, limit=600)
    narrow = payload(bot, limit=200)
    overlap = min(bar["time"] for bar in narrow["candles"])

    def marks(out):
        return sorted(
            (m["time"], m["kind"], m["price"], m["label"])
            for m in out["markers"]
            if m["kind"] in ("entry", "exit") and m["time"] >= overlap
        )

    assert marks(wide), "the overlap holds no trades, so this proves nothing"
    assert marks(wide) == marks(narrow)


def test_the_page_carries_a_trade_that_ended_on_it_and_began_before_it(
    bot_with_history, monkeypatch
):
    """An exit whose entry is off the left edge is the commonest thing on a chart.

    Dropping it left the page showing an exit from nothing — or, worse, a fresh
    entry invented by a replay that had started flat where the page did.
    """
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot, limit=60)
    oldest = min(bar["time"] for bar in out["candles"])
    straddling = [t for t in out["trades"] if t["entry_time"] < oldest]
    assert straddling, "a sixty-bar page of a 40-bar cycle held no open campaign"
    for trade in straddling:
        assert oldest <= trade["exit_time"] <= out["to_time"]


def test_dragging_past_the_start_of_the_history_is_an_end_not_an_error(
    bot_with_history, monkeypatch
):
    """The panel stops asking on `no_history`; a 500 there would be a dead chart."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot, limit=100, before=times[0])
    assert out["note"] == "no_history"
    assert out["candles"] == []


# --- what was really routed -------------------------------------------------


def started_at(run, when: int):
    """`started_at` is `auto_now_add`, so a run in the past is set after the fact."""
    from datetime import UTC, datetime

    run.started_at = datetime.fromtimestamp(when, tz=UTC)
    run.save(update_fields=["started_at"])
    return run


def entries_on(out: dict) -> list[int]:
    """The campaign entries drawn on this page, in order.

    Not ``out["trades"]``: a page carries every trade with either end inside it,
    so a campaign that opened before the left edge is in that list without an
    entry mark on the page — and a scale-out is several of its rows sharing one.
    ``unrouted`` counts marks, because that is what the operator is comparing.
    """
    return [m["time"] for m in out["markers"] if m["kind"] == "entry"]


def test_a_routed_order_is_its_own_mark_beside_the_replays_entry(bot_with_history, monkeypatch):
    """Two facts, two marks. Collapsing them hides the case that matters."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])
    run = started_at(make_run(bot), times[0])
    entry = entries_on(payload(bot))[0]
    BotAction.objects.create(
        run=run,
        bar_time=entry,
        action_type=ActionType.OPEN,
        idempotency_key="k1",
        intent={"side": "long"},
        ok=True,
    )

    out = payload(bot)
    actions = [m for m in out["markers"] if m["kind"] == "action"]
    assert [m["time"] for m in actions] == [entry]
    assert out["summary"]["actions"] == 1
    # One entry matched, the rest did not — which is the number an operator is
    # looking at this chart to find.
    assert out["summary"]["unrouted"] == len(entries_on(out)) - 1


def test_an_entry_with_nothing_decided_beside_it_is_counted(bot_with_history, monkeypatch):
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])
    started_at(make_run(bot), times[0])

    out = payload(bot)
    assert out["summary"]["unrouted"] == len(entries_on(out)) > 0


def test_a_trade_on_a_bar_the_bot_was_switched_off_for_is_not_a_discrepancy(
    bot_with_history, monkeypatch
):
    """Otherwise every page of history older than the bot screams, and the one
    that matters is lost in the noise."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    # No run at all: the bot has never been switched on for any of this.
    out = payload(bot)
    assert out["trades"]
    assert out["summary"]["unrouted"] == 0
    assert out["summary"]["watched_seconds"] == 0


def test_a_paper_bots_shadow_decision_is_not_counted_as_a_missed_trade(
    bot_with_history, monkeypatch
):
    """A shadow row routes nothing **on purpose**. Counting it as a miss would
    report every correct paper decision as a fault."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])
    run = started_at(make_run(bot), times[0])
    for index, trade in enumerate(payload(bot)["trades"]):
        BotAction.objects.create(
            run=run,
            bar_time=trade["entry_time"],
            action_type=ActionType.SHADOW,
            idempotency_key=f"s{index}",
            intent={"side": trade["side"]},
            ok=False,
        )

    assert payload(bot)["summary"]["unrouted"] == 0


def test_actions_are_read_across_every_run_not_only_the_latest(bot_with_history, monkeypatch):
    """A bot restarted this morning did not stop having traded last night."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])
    old_run = started_at(make_run(bot), times[0])
    new_run = started_at(make_run(bot), times[-50])
    for index, run in enumerate((old_run, new_run)):
        BotAction.objects.create(
            run=run,
            bar_time=times[-10 + index],
            action_type=ActionType.OPEN,
            idempotency_key=f"k{index}",
            intent={"side": "long"},
            ok=True,
        )

    out = payload(bot)
    assert out["summary"]["actions"] == 2


# --- what the payload says about itself -------------------------------------


def test_the_payload_names_the_venue_every_bar_came_from(bot_with_history, monkeypatch):
    """A chart that does not say which exchange quoted it cannot be checked."""
    bot, times = bot_with_history
    monkeypatch.setattr(chart.backtest, "last_closed_bar", lambda step, now=None: times[-1])

    out = payload(bot)
    assert out["source"] == "binance"  # the `archive` fixture's pinned provider
    assert out["symbol"] == "BTCUSDT"
    assert out["market"] == bot.market


def test_a_strategy_that_no_longer_validates_says_so_rather_than_500ing(archive, offline):
    bot = make_bot(source=CROSS, symbol="BTCUSDT", interval="15m")
    bot.strategy_version.source = "//@version=5\nstrategy('x')\nnope("
    bot.strategy_version.save(update_fields=["source"])
    seed(archive, bars=300, end=1_700_000_000 - (1_700_000_000 % STEP))

    out = payload(bot)
    assert out["note"] == "invalid_strategy"
    assert out["candles"] == []


def test_an_interval_nothing_supports_is_a_value_error_not_a_blank_chart(bot_with_history):
    bot, _ = bot_with_history
    with pytest.raises(ValueError):
        chart.payload(bot, interval="3s", limit=100)
