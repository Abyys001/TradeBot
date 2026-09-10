"""Every timeframe the panel offers, including the eight no venue serves.

Six intervals are asked of an exchange directly — 1m, 5m, 15m, 1h, 4h, 1d, the
wire values every public source in ``public_sources`` has been written and
tested against. The other eight (3m, 30m, 2h, 6h, 8h, 12h, 3d, 1w) are folded
out of those on this side rather than by inventing eight venues' wire spellings
from memory, which is what ``CLAUDE.md`` forbids and what a drifting exchange
API punishes.

What these pin: a derived bar is arithmetically the bar the venue would have
served, a *partial* bucket is never presented as a closed one, and the boundary
of a week is a Monday.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from django.test import override_settings

from apps.core.money import D
from apps.exchanges import marketdata
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import (
    DERIVED_FROM,
    INTERVALS,
    NATIVE_INTERVALS,
    Candle,
    aggregate,
    base_interval,
    base_ratio,
    bucket_start,
    is_native,
)
from apps.exchanges.marketdata import get_candles, normalise_interval
from apps.exchanges.public_stream import streamable


def bars(start: int, step: int, count: int, *, first: str = "10") -> list[Candle]:
    """``count`` bars whose close walks upward, so folding is checkable by eye."""
    out = []
    for i in range(count):
        value = D(first) + i
        out.append(
            Candle(
                time=start + i * step,
                open=value,
                high=value + 2,
                low=value - 1,
                close=value + 1,
                volume=D("1"),
            )
        )
    return out


# --- the map ----------------------------------------------------------------


def test_every_derived_interval_divides_its_base_exactly():
    """A fold that does not divide would put a bar in two buckets."""
    for interval, base in DERIVED_FROM.items():
        assert INTERVALS[interval] % INTERVALS[base] == 0, interval
        assert base in NATIVE_INTERVALS, f"{interval} is derived from a derived interval"


def test_every_offered_interval_is_native_or_derived():
    for interval in INTERVALS:
        assert is_native(interval) or interval in DERIVED_FROM, interval


def test_a_derived_interval_costs_a_small_multiple_of_base_bars():
    """Six 1h bars for a 6h bar, not three hundred 1m ones.

    The ratio is what decides how much window one page of the venue's own bars
    still covers, so a large one would quietly shorten the chart's scrollback.
    """
    assert max(base_ratio(i) for i in INTERVALS) <= 7


@pytest.mark.parametrize("interval", sorted(INTERVALS))
def test_normalise_accepts_every_offered_interval(interval):
    assert normalise_interval(interval) == interval


def test_normalise_still_refuses_something_that_is_not_a_timeframe():
    with pytest.raises(ValueError):
        normalise_interval("7s")


# --- the fold ---------------------------------------------------------------


def test_thirty_minutes_is_two_fifteen_minute_bars():
    folded = aggregate(bars(0, 900, 4), "30m")
    assert [c.time for c in folded] == [0, 1800]
    first = folded[0]
    assert first.open == D("10")  # the first sub-bar's open
    assert first.close == D("12")  # the last sub-bar's close
    assert first.high == D("13")  # the highest high across both
    assert first.low == D("9")  # the lowest low across both
    assert first.volume == D("2")  # summed, never averaged


def test_a_leading_partial_bucket_is_dropped_rather_than_half_built():
    """The first bar of a page almost never lands on a bucket edge, and a
    half-built bar written to the archive as closed is wrong forever."""
    folded = aggregate(bars(900, 900, 5), "30m")
    assert [c.time for c in folded] == [1800, 3600]


def test_the_trailing_bucket_is_kept_because_candlestore_decides_if_it_closed():
    """A forming bar is the *newest* one, and `candlestore.is_closed` already
    knows how to tell — dropping it here would lose the live bar."""
    folded = aggregate(bars(0, 900, 3), "30m")
    assert [c.time for c in folded] == [0, 1800]
    assert folded[-1].volume == D("1"), "one sub-bar so far"


def test_an_empty_page_folds_to_nothing_rather_than_raising():
    assert aggregate([], "30m") == []


def test_a_gap_in_the_base_bars_does_not_shift_later_buckets():
    """Bucket membership is computed from each bar's own time, so a missing
    sub-bar shortens one bar rather than sliding every bar after it."""
    rows = [b for b in bars(0, 900, 6) if b.time != 2700]
    folded = aggregate(rows, "30m")
    assert [c.time for c in folded] == [0, 1800, 3600]


# --- where a bucket starts --------------------------------------------------


def test_a_week_starts_on_a_monday_not_on_the_epochs_thursday():
    """Epoch second 0 is a Thursday; `t // 604800` would start weeks there."""
    wednesday = int(datetime(2024, 1, 3, 12, tzinfo=UTC).timestamp())
    start = datetime.fromtimestamp(bucket_start(wednesday, "1w"), UTC)
    assert start.weekday() == 0
    assert start == datetime(2024, 1, 1, tzinfo=UTC)


def test_an_intraday_bucket_is_aligned_to_the_utc_hour():
    at = int(datetime(2024, 6, 1, 13, 47, tzinfo=UTC).timestamp())
    assert datetime.fromtimestamp(bucket_start(at, "4h"), UTC) == datetime(
        2024, 6, 1, 12, tzinfo=UTC
    )
    assert datetime.fromtimestamp(bucket_start(at, "30m"), UTC) == datetime(
        2024, 6, 1, 13, 30, tzinfo=UTC
    )


# --- through the feed -------------------------------------------------------


def interval_aware_feed(monkeypatch, *, price: str = "100"):
    """A Binance stub that honours the interval it is asked for.

    The point is what it *records*: the source must be asked for the base
    interval, never for one Binance has never heard this platform use.
    """
    asked: list[str] = []

    def fake_get(self, url, params):
        marketdata.record_rtt(self.name, 5.0)
        if "klines" in url:
            asked.append(params["interval"])
            step = INTERVALS[params["interval"]] * 1000
            limit = int(params.get("limit") or 300)
            newest = ((int(time.time()) * 1000) // step) * step
            base = newest - step * (limit - 1)
            return [[base + i * step, price, price, price, price, "1"] for i in range(limit)]
        return {"lastPrice": price, "priceChangePercent": "0"}

    monkeypatch.setattr(marketdata.HttpSource, "_get", fake_get)
    return asked, override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]})


@pytest.mark.django_db
def test_a_thirty_minute_chart_asks_the_venue_for_fifteen_minute_bars(monkeypatch):
    asked, settings = interval_aware_feed(monkeypatch)
    with settings:
        payload = get_candles(symbol="BTCUSDT", interval="30m", market=MarketType.FUTURES, limit=20)
    assert asked == ["15m"], "the venue is never asked for an interval it does not serve"
    assert payload["interval"] == "30m"
    times = [candle["t"] for candle in payload["candles"]]
    assert times, "a 30m chart is not empty"
    assert all(t % 1800 == 0 for t in times)
    assert all(b - a == 1800 for a, b in zip(times, times[1:], strict=False))


@pytest.mark.django_db
def test_a_native_interval_is_still_a_straight_pass_to_the_venue(monkeypatch):
    asked, settings = interval_aware_feed(monkeypatch)
    with settings:
        get_candles(symbol="BTCUSDT", interval="4h", market=MarketType.FUTURES, limit=10)
    assert asked == ["4h"]


@pytest.mark.django_db
@pytest.mark.parametrize("interval", sorted(DERIVED_FROM))
def test_every_derived_interval_serves_a_chart(monkeypatch, interval):
    asked, settings = interval_aware_feed(monkeypatch)
    with settings:
        payload = get_candles(
            symbol="BTCUSDT", interval=interval, market=MarketType.FUTURES, limit=10
        )
    assert asked == [base_interval(interval)]
    step = INTERVALS[interval]
    times = [candle["t"] for candle in payload["candles"]]
    assert times
    assert all(b - a == step for a, b in zip(times, times[1:], strict=False))


# --- streaming --------------------------------------------------------------


def test_nothing_streams_a_derived_interval_so_the_chart_polls_it():
    """No venue publishes a 30m kline subscription this platform speaks, and
    eight handshakes that each die on a KeyError is not a fallback."""
    assert streamable(["binance", "bybit"], "30m") == []
    assert streamable(["binance", "bybit"], "1h") == ["binance", "bybit"]
