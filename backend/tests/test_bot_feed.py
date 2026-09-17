"""Q23 / Phase 3 — confirmed bars, exactly once each, in order, or the bot stops."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings
from django.test import override_settings

from apps.bots.feed import (
    BarFeed,
    FeedGap,
    NotEnoughHistory,
    interval_seconds,
    is_confirmed,
    to_bar,
    untraded,
    warmup_bars_needed,
)
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import Candle

D = Decimal


def candle(time: int, close: str = "100") -> Candle:
    price = D(close)
    return Candle(time=time, open=price, high=price, low=price, close=price, volume=D("1"))


def feed(interval: str = "15m") -> BarFeed:
    return BarFeed(symbol="BTCUSDT", interval=interval, market=MarketType.FUTURES)


def bot_settings_with(**overrides) -> dict:
    return {**settings.BOT, **overrides}


# --- intervals --------------------------------------------------------------


@pytest.mark.parametrize(
    ("interval", "seconds"), [("1m", 60), ("5m", 300), ("15m", 900), ("1h", 3600), ("1d", 86400)]
)
def test_interval_seconds(interval, seconds):
    assert interval_seconds(interval) == seconds


def test_an_unsupported_interval_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        interval_seconds("3s")


# --- Q23: only closed bars --------------------------------------------------


def test_a_bar_still_forming_is_not_confirmed():
    """A decision made on a moving bar can reverse before it stops."""
    assert is_confirmed(1000, "15m", now=1000 + 800) is False


def test_a_bar_is_confirmed_once_its_interval_and_the_lag_have_passed():
    lag = settings.BOT["BAR_CONFIRM_LAG_MS"] / 1000
    assert is_confirmed(1000, "15m", now=1000 + 900 + lag) is True


def test_the_confirmation_lag_is_required_not_just_the_interval():
    """Exchanges emit the closing update slightly late."""
    with override_settings(BOT=bot_settings_with(BAR_CONFIRM_LAG_MS=5000)):
        assert is_confirmed(1000, "15m", now=1000 + 900 + 1) is False
        assert is_confirmed(1000, "15m", now=1000 + 900 + 5) is True


# --- warm-up ----------------------------------------------------------------


def test_warmup_is_a_multiple_of_the_lookback_not_the_lookback():
    """A seeded rma is arithmetically defined after `length` bars and not yet
    converged; reading it immediately does not match TradingView."""
    lookback = settings.BOT["WARMUP_MIN_BARS"]  # comfortably above the floor
    assert warmup_bars_needed(lookback) == lookback * settings.BOT["WARMUP_MULTIPLIER"]


def test_warmup_has_a_floor_for_a_script_with_no_indicators():
    assert warmup_bars_needed(0) == settings.BOT["WARMUP_MIN_BARS"]


def test_not_enough_history_says_what_it_had_and_what_it_needed():
    error = NotEnoughHistory(40, 200)
    assert "40" in str(error) and "200" in str(error)


# --- ordering and gaps ------------------------------------------------------


async def test_a_bar_already_delivered_is_not_delivered_twice():
    f = feed()
    f.last_bar_time = 900
    assert await f._accept(candle(900), "test") == []


async def test_a_bar_still_forming_is_not_accepted():
    import time

    f = feed()
    # The bar that is open *right now*, so nothing before it is missing either.
    now = int(time.time())
    current = now - now % 900
    f.last_bar_time = current - 900
    assert await f._accept(candle(current), "test") == []


async def test_the_next_bar_in_sequence_is_accepted():
    f = feed()
    f.last_bar_time = 900
    accepted = await f._accept(candle(1800), "test")
    assert [item.bar.time for item in accepted] == [1800]
    assert f.last_bar_time == 1800


async def test_a_repaired_bar_is_yielded_before_the_bar_that_exposed_the_gap():
    """The runtime must never see the future before the past."""
    f = feed()
    f.last_bar_time = 900
    f._repair = _fake_repair([candle(1800)])
    accepted = await f._accept(candle(2700), "test")
    assert [item.bar.time for item in accepted] == [1800, 2700]
    assert accepted[0].repaired is True
    assert accepted[1].repaired is False


async def test_a_gap_is_counted_even_when_it_is_repaired():
    f = feed()
    f.last_bar_time = 900
    f._repair = _fake_repair([candle(1800)])
    await f._accept(candle(2700), "test")
    assert f.gaps == 1
    assert f.gaps_repaired == 1


async def test_a_gap_that_cannot_be_repaired_stops_the_bot():
    """Q25: the strategy's state machine now disagrees with the market, and
    carrying on is trading a position it thinks it understands."""

    async def refuse(start, end):
        raise FeedGap("cannot repair", missing=[1800])

    f = feed()
    f.last_bar_time = 900
    f._repair = refuse
    with pytest.raises(FeedGap):
        await f._accept(candle(2700), "test")


def filler(time: int, price: str = "100") -> Candle:
    """What Hyperliquid serves for a slot in which nothing traded."""
    p = D(price)
    return Candle(time=time, open=p, high=p, low=p, close=p, volume=D("0"))


def test_a_flat_zero_volume_candle_is_untraded():
    assert untraded(filler(900)) is True


def test_a_flat_candle_that_traded_is_a_bar():
    assert untraded(candle(900)) is False


def test_zero_volume_with_a_range_is_a_bar():
    """A feed that omits volume must not lose every bar it serves."""
    bar = Candle(time=900, open=D(100), high=D(101), low=D(99), close=D(100), volume=D(0))
    assert untraded(bar) is False


async def test_an_untraded_slot_advances_the_feed_without_reaching_the_strategy():
    """TradingView draws nothing there, so the script must see nothing either."""
    f = feed()
    f.last_bar_time = 900
    assert await f._accept(filler(1800), "test") == []
    assert f.last_bar_time == 1800
    accepted = await f._accept(candle(2700), "test")
    assert [item.bar.time for item in accepted] == [2700]
    assert f.gaps == 0


async def test_a_slot_the_venue_answers_with_a_filler_is_not_a_gap(monkeypatch):
    """The stream may skip a quiet slot; the refetch then finds the filler. The
    slot is accounted for, and stopping the bot over it would be a false alarm."""
    from apps.exchanges import marketdata

    quiet = {"t": 1800, "o": "100", "h": "100", "l": "100", "c": "100", "v": "0"}
    monkeypatch.setattr(marketdata, "get_candles", lambda **_: {"candles": [quiet]})
    f = feed()
    f.last_bar_time = 900
    accepted = await f._accept(candle(2700), "test")
    assert [item.bar.time for item in accepted] == [2700]


def test_a_feed_gap_names_the_bars_it_is_missing():
    gap = FeedGap("gone", missing=[1800, 2700])
    assert gap.missing == [1800, 2700]


# --- conversion -------------------------------------------------------------


def test_a_candle_becomes_a_bar_in_decimal():
    bar = to_bar(candle(900, "123.45"))
    assert bar.time == 900
    assert bar.close == D("123.45")
    assert all(isinstance(v, Decimal) for v in (bar.open, bar.high, bar.low, bar.close))


def test_the_bar_time_is_the_open_time():
    """Everything downstream keys on it — the idempotency key included."""
    assert to_bar(candle(900)).time == 900


def _fake_repair(candles):
    async def repair(start, end):
        return candles

    return repair


# --- a close the venue never flags ------------------------------------------
#
# Hyperliquid — the pinned market-data venue — marks a candle's end with `T`,
# the last millisecond it accepts trades, and stops sending frames for that bar
# *before* `T` passes. So the final frame a bar ever gets is computed
# `closed=False`. It is flagged only when a frame happens to land after `T`,
# which is luck: measured live on ZECUSDC 1m, one run saw four complete bars and
# 118 updates without a single flag, a second saw one flag in five bars. A feed
# waiting on that flag therefore loses most bars and stalls indefinitely on a
# quiet pair, which is why every bot run on this platform so far had
# `bars_evaluated = 0` while looking perfectly healthy.


def now_bar(interval: str = "15m") -> tuple[int, int]:
    """The bar open time that is forming *right now*, and the step.

    Rollover is defined against the wall clock — a bar is finished when its own
    window has closed — so these have to be real times rather than a convenient
    small integer, or every one of them is already hours past.
    """
    import time

    step = interval_seconds(interval)
    now = int(time.time())
    return now - now % step, step


def no_catch_up(f: BarFeed) -> BarFeed:
    """Silence the REST catch-up, which has its own tests below.

    These fixtures park the feed one bar behind on purpose, which is exactly
    the state the catch-up exists to notice.
    """

    async def _none(provider: str) -> list:
        return []

    f._catch_up = _none  # type: ignore[assignment]
    return f


async def test_a_later_bar_arriving_proves_the_one_before_it_finished():
    """The signal that does arrive, when the flag never does."""
    f = no_catch_up(feed())
    current, step = now_bar()
    previous = current - step
    f.last_bar_time = previous - step

    with override_settings(BOT=bot_settings_with(BAR_CONFIRM_LAG_MS=86_400_000)):
        # Updates to the bar that is still forming release nothing, and neither
        # does the clock while the confirmation lag has not passed.
        assert await f._rollover(candle(previous), "test") == []
        assert await f._rollover(candle(previous, "101"), "test") == []
        assert await f._rollover(candle(current), "test") == []

    # The venue has moved on and the lag has passed — and it is the *last*
    # state seen of the previous bar that is delivered, not the first.
    released = await f._rollover(candle(current, "102"), "test")
    assert [item.bar.time for item in released] == [previous]
    assert released[0].bar.close == D("101")


async def test_a_rolled_over_bar_waits_out_the_confirmation_lag_rather_than_being_dropped():
    """Q23 still decides when a finished bar may be *used*."""
    f = no_catch_up(feed())
    current, step = now_bar()
    previous = current - step
    f.last_bar_time = previous - step

    with override_settings(BOT=bot_settings_with(BAR_CONFIRM_LAG_MS=86_400_000)):
        assert await f._rollover(candle(previous), "test") == []
        assert await f._rollover(candle(current), "test") == []
        assert [row.time for row in f._finished] == [previous]

    # Held, not thrown away: the next update admits it once the lag has passed.
    released = await f._rollover(candle(current, "101"), "test")
    assert [item.bar.time for item in released] == [previous]


async def test_rollover_never_delivers_the_bar_that_is_still_forming():
    f = no_catch_up(feed())
    current, step = now_bar()
    previous = current - step
    f.last_bar_time = previous - step
    await f._rollover(candle(previous), "test")
    await f._rollover(candle(current), "test")
    # `current` is the open bar now. Nothing has proved it finished.
    assert f.last_bar_time == previous


# --- a stream that stays up and stops moving ---------------------------------
#
# The other half of the same lesson, and the one that stopped the bot on
# 2026-09-14. Rollover is defined as "a later bar arrived". A Hyperliquid socket
# on ZECUSDC 30m kept sending frames — the 90s idle timeout never fired, and the
# venue only closed it with "Expired" two hours later — without a single frame
# ever carrying a later bar. Nothing rolled over, so the bot evaluated nothing
# from 17:30 onward, and the first thing to notice was Q25's no-bars auto-stop,
# which stopped the bot rather than the stall.


async def test_a_bar_whose_window_has_closed_is_released_without_a_later_one():
    """The clock is the second signal, for when the venue never sends a third."""
    f = no_catch_up(feed())
    current, step = now_bar()
    previous = current - step
    f.last_bar_time = previous - step

    # One frame, for a bar that has already closed, and never another for a
    # later one. It is finished whatever the venue does next.
    released = await f._rollover(candle(previous, "101"), "test")
    assert [item.bar.time for item in released] == [previous]


async def test_a_stream_republishing_one_bar_does_not_freeze_the_feed():
    """Frames keep arriving, none of them later. The feed must still move."""
    f = no_catch_up(feed())
    current, step = now_bar()
    previous = current - step
    f.last_bar_time = previous - step

    delivered = [item.bar.time for item in await f._rollover(candle(previous), "test")]
    # The same bar, again and again. Delivered once, and never twice.
    for _ in range(5):
        delivered += [item.bar.time for item in await f._rollover(candle(previous), "test")]
    assert delivered == [previous]


async def test_a_closing_flag_inside_the_confirmation_lag_does_not_lose_the_bar(monkeypatch):
    """The venue's own ``closed`` flag used to *discard* the bar it named.

    ``_forming`` was cleared and the candle handed straight to ``_accept``,
    which refuses a bar still inside ``BAR_CONFIRM_LAG_MS`` — so nothing held
    it and nothing could roll it over afterwards. On an active pair the first
    frame past ``T`` almost always lands inside that lag, which is where the
    recurring "1 bar(s) missing — refetching" came from.
    """
    from apps.exchanges.public_stream import BarUpdate, StreamDown

    f = no_catch_up(feed())
    current, step = now_bar()
    previous = current - step
    f.last_bar_time = previous - step

    frames = [
        # Flagged closed by the venue, but only just — inside the lag, so
        # `_accept` will not take it yet.
        ("hyperliquid", BarUpdate(candle=candle(previous, "101"), closed=True)),
        # ...and then the next bar, as the venue moves on and the lag passes.
        ("hyperliquid", BarUpdate(candle=candle(current), closed=False)),
    ]
    lags = iter([False, True, True, True])

    def confirmed(open_time, interval, now=None):
        if open_time >= current:
            return False
        return next(lags, True)

    async def fake_stream_bars(**kwargs):
        for frame in frames:
            yield frame

    monkeypatch.setattr("apps.bots.feed.is_confirmed", confirmed)
    out = [item.bar.time async for item in f._stream([], fake_stream_bars, StreamDown)]
    assert out == [previous], "the flagged bar was dropped instead of held"


async def test_a_feed_left_behind_the_market_catches_up_over_rest(monkeypatch):
    """The safety net under the clock release, for a stream frozen *behind*.

    Neither rollover nor the clock can reach a socket that never names a bar
    later than one already delivered: there is nothing to promote. The wall
    clock can see it, and the REST source the repair path already uses has the
    bars.
    """
    f = feed("30m")
    current, step = now_bar("30m")
    f.last_bar_time = current - 5 * step

    wanted = [current - 4 * step, current - 3 * step, current - 2 * step, current - step]
    payload = {
        "source": "hyperliquid",
        "candles": [
            {"t": t, "o": "100", "h": "101", "l": "99", "c": "100", "v": "5"}
            for t in [*wanted, current]
        ],
    }
    monkeypatch.setattr("apps.exchanges.marketdata.get_candles", lambda **kwargs: payload)

    released = await f._catch_up("hyperliquid")
    assert [item.bar.time for item in released] == wanted
    assert f.last_bar_time == wanted[-1], "the bar still forming is not delivered"


async def test_the_catch_up_leaves_a_stream_that_is_merely_between_bars_alone():
    """It must never race the stream's own delivery."""
    f = feed("30m")
    current, step = now_bar("30m")
    # One bar behind: the ordinary state between "a bar closed" and "it arrived".
    f.last_bar_time = current - step
    assert await f._catch_up("hyperliquid") == []


async def test_a_failed_catch_up_fetch_is_not_a_gap(monkeypatch):
    """One unreachable fetch is a retry, not a reason to stop a live bot."""
    f = feed("30m")
    current, step = now_bar("30m")
    f.last_bar_time = current - 5 * step

    def boom(**kwargs):
        raise RuntimeError("no route to host")

    monkeypatch.setattr("apps.exchanges.marketdata.get_candles", boom)
    assert await f._catch_up("hyperliquid") == []
    assert f.last_bar_time == current - 5 * step


# --- the archive ------------------------------------------------------------
#
# The platform's rule is that every closed bar it sees is kept
# (`apps/exchanges/candlestore.py`). This feed was the one path that read bars
# and threw them away, so the archive had holes in it exactly where a bot had
# been running — a panel nobody has open is not archiving either, and the hole
# that made Q38 harder to diagnose was fourteen hours wide.


@pytest.mark.django_db
async def test_every_bar_the_feed_admits_is_archived(monkeypatch):
    from apps.exchanges import candlestore

    written: list[tuple[str, int]] = []
    monkeypatch.setattr(
        candlestore,
        "persist_quietly",
        lambda **kw: written.extend((kw["exchange"], c.time) for c in kw["candles"]),
    )
    monkeypatch.setattr("apps.exchanges.marketdata.pinned_provider", lambda: "hyperliquid")

    f = feed()
    f.last_bar_time = 900
    await f._accept(candle(1800), "test")

    assert written == [("hyperliquid", 1800)]


@pytest.mark.django_db
async def test_a_repaired_bar_is_archived_too(monkeypatch):
    """It is as real as any other — the gap is in the delivery, not the market."""
    from apps.exchanges import candlestore

    written: list[int] = []
    monkeypatch.setattr(
        candlestore,
        "persist_quietly",
        lambda **kw: written.extend(c.time for c in kw["candles"]),
    )
    monkeypatch.setattr("apps.exchanges.marketdata.pinned_provider", lambda: "hyperliquid")

    f = feed()
    f.last_bar_time = 900
    f._repair = _fake_repair([candle(1800)])
    await f._accept(candle(2700), "test")

    assert sorted(written) == [1800, 2700]


@pytest.mark.django_db
async def test_a_failed_archive_write_never_costs_a_bar(monkeypatch):
    """The archive is a side effect of running; a database that will not take
    the write degrades to "no history recorded", never to a bot that is blind."""
    from apps.exchanges import candlestore

    def boom(**_):
        raise RuntimeError("disk full")

    monkeypatch.setattr(candlestore, "persist", boom)
    monkeypatch.setattr("apps.exchanges.marketdata.pinned_provider", lambda: "hyperliquid")

    f = feed()
    f.last_bar_time = 900
    accepted = await f._accept(candle(1800), "test")

    assert [item.bar.time for item in accepted] == [1800]


@pytest.mark.django_db
def test_a_bar_with_no_venue_to_attribute_it_to_is_dropped_rather_than_mislabelled(
    monkeypatch,
):
    """`marketdata.get_candles` refuses another exchange's bars under a pinned
    badge, so a row stored with the wrong provenance is one that can never be
    read back."""
    from apps.exchanges import candlestore

    monkeypatch.setattr(candlestore, "persist_quietly", lambda **_: 1 / 0)
    monkeypatch.setattr("apps.exchanges.marketdata.pinned_provider", lambda: "")

    f = feed()
    assert f._archive([candle(1800)]) == 0
