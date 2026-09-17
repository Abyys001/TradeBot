"""The same settings, twice, must produce the same report.

The admin's words: *running two backtests with exactly the same settings
sometimes produces different results*. It was true, and the cause was not in
the replay — that has always been a pure function of its bars, which is what
``intent_digest`` exists to prove. It was in **which bars the run got**.

Three things conspired, and each is one test below.

  1. The window's end came off the date picker as "today, 23:59", which for
     most of the day is in the **future**. No archive can hold a bar that has
     not closed, so the window was never covered, every run re-downloaded, and
     a run at 14:00 and a run at 16:00 legitimately replayed different bars.

  2. The download paged back from **now** rather than from the end of the
     window, so a backtest of last spring spent its budget on this week before
     reaching a bar it would replay.

  3. It stopped on a **wall clock** — ninety seconds — so a window reaching
     further back than the venue serves was re-walked on every run and came
     back short by a different amount each time. A second run, resuming from a
     deeper archive, then replayed a longer series than the first.

The fix is that the window is pulled back to the last closed bar, the walk
starts at that end, and a venue's proved history floor is remembered
(``trading.SeriesFloor``) so a window that reaches past it counts as covered.
"""

from __future__ import annotations

import time
from decimal import Decimal as D

import pytest

from apps.bots import backtest
from apps.exchanges.base import MarketType
from tests import pine_corpus

STEP = 3600
SOURCE = (pine_corpus.ACCEPT / "01_sma_cross.pine").read_text()


class _Source:
    """A venue with a fixed, finite history, paged newest-first."""

    page_limit = 5

    def __init__(self, times):
        from apps.exchanges.candlestore import Candle

        self.calls = 0
        self.ends: list[int | None] = []
        self.all = [
            Candle(
                time=t,
                open=D("100"),
                high=D("101"),
                low=D("99"),
                close=D("100"),
                volume=D("1"),
            )
            for t in sorted(times)
        ]

    def candles(self, *, symbol, interval, market, limit, end=None):
        self.calls += 1
        self.ends.append(end)
        rows = [c for c in self.all if end is None or c.time <= end]
        return rows[-min(limit, self.page_limit):]


def serve(monkeypatch, source):
    monkeypatch.setattr("apps.exchanges.marketdata.source_for", lambda name, **kw: source)
    return source


def window(**overrides):
    return {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "market": MarketType.FUTURES,
        "from_time": 100 * STEP,
        "to_time": 140 * STEP,
        "warmup": 5,
        **overrides,
    }


# --- 1. a window that ends in the future ------------------------------------


def test_the_window_ends_on_the_last_closed_bar_not_on_the_date_picker(archive, monkeypatch):
    """"To: today" is a moment in the future for most of the day.

    Left alone it is a window whose contents change under the operator between
    one run and the next — and a report that moves is not a report.
    """
    now = int(time.time())
    recent = [(now // STEP - n) * STEP for n in range(1, 60)]
    serve(monkeypatch, _Source(recent))
    result = backtest.load_bars(
        **window(from_time=recent[-1], to_time=now + 10 * STEP)
    )
    assert result.covers_to <= backtest.last_closed_bar(STEP)
    assert max(bar.time for bar in result.bars) <= result.covers_to


def test_last_closed_bar_is_on_the_grid_so_two_runs_a_minute_apart_agree():
    at = 1_000_000_000
    assert backtest.last_closed_bar(STEP, now=at) == backtest.last_closed_bar(STEP, now=at + 59)
    assert backtest.last_closed_bar(STEP, now=at) % STEP == 0


# --- 2. the walk starts at the window, not at the clock ---------------------


def test_the_download_pages_back_from_the_end_of_the_window(archive, monkeypatch):
    """A backtest of last spring must not spend its budget on this week."""
    source = serve(monkeypatch, _Source([n * STEP for n in range(1, 200)]))
    backtest.load_bars(**window())
    assert source.ends, "nothing was fetched"
    # The very first request is bounded by the window, not left open-ended at
    # "now" — which is what `end=None` used to mean.
    assert source.ends[0] == 140 * STEP


# --- 3. the venue's floor is remembered -------------------------------------


def test_a_window_reaching_past_the_venues_history_is_not_re_walked_every_run(
    archive, monkeypatch
):
    """The case that made two identical runs differ.

    The venue holds bars 50..199 and the request starts at 1. The first run
    walks to the bottom and learns where the bottom is; the second must read
    the archive and stop, because the bars it is "missing" do not exist
    anywhere and asking again is a guaranteed-empty download on a clock.
    """
    source = serve(monkeypatch, _Source([n * STEP for n in range(50, 200)]))
    asked = window(from_time=1 * STEP, to_time=140 * STEP, warmup=0)

    first = backtest.load_bars(**asked)
    assert first.downloaded > 0
    calls_after_first = source.calls

    second = backtest.load_bars(**asked)
    assert second.downloaded == 0
    assert source.calls == calls_after_first, "it walked the whole series again"
    assert [bar.time for bar in second.bars] == [bar.time for bar in first.bars]


def test_two_runs_of_the_same_window_replay_the_same_bars(archive, monkeypatch):
    serve(monkeypatch, _Source([n * STEP for n in range(1, 200)]))
    asked = window()
    first = backtest.load_bars(**asked)
    second = backtest.load_bars(**asked)
    assert [b.time for b in first.bars] == [b.time for b in second.bars]
    assert [b.close for b in first.bars] == [b.close for b in second.bars]


# --- and the replay itself ---------------------------------------------------


def _report(bars):
    return backtest.run(
        source=SOURCE,
        symbol="BTCUSDT",
        interval="1h",
        from_time=bars[0].time,
        to_time=bars[-1].time,
        bars=bars,
    )


def test_the_same_bars_produce_a_byte_identical_report(archive, monkeypatch):
    """The replay has always been pure; this is what says so out loud.

    Everything a reader compares between two runs — the digest, every metric,
    every trade — is asserted equal, not just the digest, because the digest
    covers intents and a report is also arithmetic over fills.
    """
    serve(monkeypatch, _Source([n * STEP for n in range(1, 200)]))
    bars = backtest.load_bars(**window()).bars

    first, second = _report(bars), _report(list(bars))

    assert first.intent_digest == second.intent_digest
    assert first.metrics == second.metrics
    assert [t.as_dict() for t in first.trades] == [t.as_dict() for t in second.trades]
    assert first.equity_curve == second.equity_curve


@pytest.mark.django_db
def test_the_report_says_which_window_it_actually_covered(archive, monkeypatch):
    """A clamped end is stated, never silently applied.

    The operator asked for one window and got another; a report that did not
    say so would be answering a question nobody asked.
    """
    now = int(time.time())
    recent = [(now // STEP - n) * STEP for n in range(1, 60)]
    serve(monkeypatch, _Source(recent))
    report = backtest.run(
        source=SOURCE,
        symbol="BTCUSDT",
        interval="1h",
        from_time=recent[-1],
        to_time=now + 10 * STEP,
    )
    assert report.to_time <= backtest.last_closed_bar(STEP)
    assert report.data_source["requested_to"] > report.data_source["covers_to"]
    assert any("closed at" in line for line in report.warnings)
