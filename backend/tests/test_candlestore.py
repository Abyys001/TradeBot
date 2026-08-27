"""The candle archive: persist, read, merge, idempotency.

`candlestore` is the single module that writes to and reads from
`StoredCandle`. These tests exercise it in isolation — no HTTP stubs,
no market data settings, just the archive logic against a real Postgres.
"""

from __future__ import annotations

import time

import pytest

from apps.core.money import D
from apps.exchanges.base import MarketType
from apps.exchanges.candlestore import (
    is_closed,
    merge,
    newest_stored,
    oldest_stored,
    persist,
    read_window,
)
from apps.exchanges.feed_base import INTERVALS, Candle
from apps.trading.models import StoredCandle

NOW = int(time.time())


def _candle(open_time: int, **overrides) -> Candle:
    defaults = {"open": D("100"), "high": D("101"), "low": D("99"), "close": D("100"), "volume": D("1")}
    defaults.update(overrides)
    return Candle(time=open_time, **defaults)


# --- is_closed ---------------------------------------------------------------


class TestIsClosed:
    def test_a_bar_whose_interval_has_elapsed_is_closed(self):
        bar = _candle(NOW - 120)
        assert is_closed(bar, "1m") is True

    def test_a_bar_still_within_its_interval_is_not_closed(self):
        now = int(time.time())
        bar = _candle(now - 30)
        assert is_closed(bar, "1m", now=now) is False

    def test_an_unknown_interval_returns_false(self):
        bar = _candle(NOW - 99999)
        assert is_closed(bar, "nonsense") is False

    def test_boundary_exactly_at_close(self):
        step = INTERVALS["5m"]
        bar = _candle(NOW - step)
        assert is_closed(bar, "5m") is True

    def test_one_second_before_close(self):
        step = INTERVALS["5m"]
        now = int(time.time())
        bar = _candle(now - step + 1)
        assert is_closed(bar, "5m", now=now) is False

    def test_now_override(self):
        bar = _candle(1000)
        assert is_closed(bar, "1m", now=1000 + 60) is True
        assert is_closed(bar, "1m", now=1000 + 59) is False


# --- persist -----------------------------------------------------------------


@pytest.mark.django_db
class TestPersist:
    def test_closed_bars_are_written(self):
        bars = [_candle(NOW - i * 120) for i in range(5)]
        written = persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=bars,
        )
        assert written == 5
        assert StoredCandle.objects.filter(symbol="BTCUSDT").count() == 5

    def test_idempotent_re_persist_ignores_settled_duplicates(self):
        bars = [_candle(NOW - i * 120) for i in range(3)]
        persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=bars,
        )
        persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=bars,
        )
        assert StoredCandle.objects.filter(symbol="BTCUSDT").count() == 3

    def test_unsettled_bars_are_upserted(self):
        step = INTERVALS["1m"]
        # This bar is still forming — within the last interval.
        forming_time = NOW - 10
        bars = [_candle(forming_time, close=D("50"))]
        persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=bars,
        )
        row = StoredCandle.objects.get(symbol="BTCUSDT", open_time=forming_time)
        assert row.close == D("50")

        # Re-persist with updated close — should overwrite.
        bars2 = [_candle(forming_time, close=D("55"))]
        persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=bars2,
        )
        row.refresh_from_db()
        assert row.close == D("55")
        assert StoredCandle.objects.filter(symbol="BTCUSDT").count() == 1

    def test_since_skips_older_settled_bars(self):
        old = _candle(NOW - 600)
        new = _candle(NOW - 120)
        persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=[old],
        )
        written = persist(
            exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES,
            interval="1m", candles=[old, new],
            since=NOW - 300,
        )
        assert written == 1
        assert StoredCandle.objects.filter(symbol="BTCUSDT").count() == 2

    def test_empty_exchange_or_symbol_writes_nothing(self):
        bars = [_candle(NOW - 120)]
        assert persist(exchange="", symbol="X", market=MarketType.FUTURES, interval="1m", candles=bars) == 0
        assert persist(exchange="binance", symbol="", market=MarketType.FUTURES, interval="1m", candles=bars) == 0
        assert StoredCandle.objects.count() == 0

    def test_different_exchanges_are_kept_separate(self):
        bar = _candle(NOW - 120)
        persist(exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=[bar])
        persist(exchange="bybit", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=[bar])
        assert StoredCandle.objects.filter(symbol="BTCUSDT").count() == 2

    def test_different_intervals_are_kept_separate(self):
        bar = _candle(NOW - 120)
        persist(exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=[bar])
        persist(exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES, interval="5m", candles=[bar])
        assert StoredCandle.objects.filter(symbol="BTCUSDT").count() == 2


# --- newest_stored / oldest_stored ------------------------------------------


@pytest.mark.django_db
class TestNewestAndOldestStored:
    def test_returns_none_when_empty(self):
        assert newest_stored(symbol="X", interval="1m", market=MarketType.FUTURES) is None
        assert oldest_stored(symbol="X", interval="1m", market=MarketType.FUTURES) is None

    def test_newest_after_persist(self):
        bars = [_candle(NOW - i * 120) for i in range(5)]
        persist(exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=bars)
        assert newest_stored(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES) == bars[0].time

    def test_oldest_after_persist(self):
        bars = [_candle(NOW - i * 120) for i in range(5)]
        persist(exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=bars)
        assert oldest_stored(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES) == bars[-1].time

    def test_exchange_filter(self):
        persist(exchange="binance", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=[_candle(NOW - 120)])
        persist(exchange="bybit", symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=[_candle(NOW - 240)])
        assert newest_stored(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, exchange="bybit") == NOW - 240


# --- read_window -------------------------------------------------------------


@pytest.mark.django_db
class TestReadWindow:
    def _seed(self, n: int = 10, exchange: str = "binance") -> list[int]:
        """Insert n closed bars one minute apart, newest first."""
        times = [NOW - i * 60 for i in range(n)]
        bars = [_candle(t) for t in times]
        persist(exchange=exchange, symbol="BTCUSDT", market=MarketType.FUTURES, interval="1m", candles=bars)
        return times

    def test_returns_bars_oldest_first(self):
        times = self._seed()
        result, source = read_window(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=5)
        assert len(result) == 5
        assert [c.time for c in result] == sorted([c.time for c in result])
        assert source == "binance"

    def test_end_cursor_filters_to_before_that_moment(self):
        times = self._seed()
        end = times[3]  # the 4th-newest bar
        result, _ = read_window(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=100, end=end)
        assert all(c.time <= end for c in result)
        assert any(c.time == end for c in result)

    def test_returns_none_when_empty(self):
        result = read_window(symbol="NOPE", interval="1m", market=MarketType.FUTURES, limit=10)
        assert result is None

    def test_exchange_filter(self):
        self._seed(exchange="binance")
        self._seed(n=3, exchange="bybit")
        result, source = read_window(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=100, exchange="bybit")
        assert len(result) == 3
        assert source == "bybit"

    def test_limit_caps_results(self):
        self._seed(n=20)
        result, _ = read_window(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=5)
        assert len(result) == 5


# --- merge -------------------------------------------------------------------


class TestMerge:
    def test_live_wins_on_collision(self):
        stored = [_candle(100, close=D("10"))]
        live = [_candle(100, close=D("20"))]
        result = merge(stored, live)
        assert len(result) == 1
        assert result[0].close == D("20")

    def test_union_is_oldest_first(self):
        stored = [_candle(200), _candle(100)]
        live = [_candle(300), _candle(250)]
        result = merge(stored, live)
        assert [c.time for c in result] == [100, 200, 250, 300]

    def test_empty_stored(self):
        live = [_candle(100), _candle(200)]
        result = merge([], live)
        assert [c.time for c in result] == [100, 200]

    def test_empty_live(self):
        stored = [_candle(100), _candle(200)]
        result = merge(stored, [])
        assert [c.time for c in result] == [100, 200]

    def test_both_empty(self):
        assert merge([], []) == []
