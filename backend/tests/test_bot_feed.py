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
