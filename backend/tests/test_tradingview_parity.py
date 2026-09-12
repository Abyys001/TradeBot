"""A TradingView Strategy Tester run, replayed bar for bar against its own List of Trades.

McGinley T3 Flow Campaign on Hyperliquid **spot** UZEC/USDC, 30m, UTC, the
Properties tab exactly as the admin ran it. Provenance, and the twelve CSV rows
whose exit columns had to be rebuilt, are in the fixture's README.

The venue keeps 5000 bars of 30m, so the replay starts on 2026-05-31 and trades
from 2026-06-19 — past every indicator's convergence — against the 21 rows of
TradingView's list that open on or after it. TradingView is never flat on this
script, so the replay cannot start holding what TradingView held; it starts
flat on TradingView's equity instead, and that is the one inexactness here: the
first campaign is sized without the exit fee of the leg TradingView was still
closing. Every campaign after it is checked to the cent.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from apps.bots import backtest
from apps.pine.bar import Bar
from tests import pine_corpus

D = Decimal
HERE = Path(__file__).parent / "fixtures" / "pine" / "tradingview" / "mcg_t3_flow"
SOURCE = (pine_corpus.ACCEPT / "27_published_strategy.pine").read_text()
WINDOW_FROM = "2026-06-19 00:00"
#: The first campaign carries the seeding inexactness described above.
FIRST_EXACT_TRADE = 44
#: Entry sizes as TradingView prints them on the chart, four decimals.
CHART_LABELS = {
    "2026-07-01 20:00": D("79.5183"),
    "2026-07-22 01:00": D("63.9283"),
    "2026-08-02 22:00": D("70.1105"),
    "2026-08-11 06:00": D("70.7931"),
    "2026-08-17 14:30": D("66.8662"),
    "2026-09-11 09:30": D("34.8691"),
}


def utc(text: str) -> int:
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())


def _bars() -> list[Bar]:
    with open(HERE / "bars_hl_spot_uzec_30m.csv") as fh:
        return [
            Bar(
                time=int(row["time"]),
                open=D(row["open"]),
                high=D(row["high"]),
                low=D(row["low"]),
                close=D(row["close"]),
                volume=D(row["volume"]),
            )
            for row in csv.DictReader(fh)
        ]


def _tradingview() -> list[dict]:
    with open(HERE / "list_of_trades.csv") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def replay():
    tv = _tradingview()
    start = utc(WINDOW_FROM)
    # TradingView's equity once everything before the window has closed.
    equity = D(100000) + sum(
        D(row["pnl_usdc"])
        for row in tv
        if row["exit_time_utc"] and utc(row["exit_time_utc"]) <= start + 3600
    )
    bars = _bars()
    report = backtest.run(
        source=SOURCE,
        symbol="UZECUSDC",
        interval="30m",
        from_time=start,
        to_time=bars[-1].time,
        bars=bars,
        mintick=D("0.1"),
        price_tick=D("0.1"),
        qty_step=D("0.0001"),
        inputs={"startTime": utc("2026-03-01 13:00") * 1000},
        property_overrides={"initial_capital": equity},
    )
    theirs = [row for row in tv if utc(row["entry_time_utc"]) >= start]
    return report.trades, theirs


def test_every_trade_opens_and_closes_on_the_bar_and_at_the_price_tradingview_did(replay):
    ours, theirs = replay
    assert len(ours) == len(theirs) == 21
    for mine, row in zip(ours, theirs, strict=True):
        where = f"trade {row['trade']}"
        assert mine.side == row["side"], where
        assert mine.entry_time == utc(row["entry_time_utc"]), where
        assert mine.entry_price == D(row["entry_price"]), where
        if row["exit_time_utc"]:  # the last row is still open on TradingView
            assert mine.exit_time == utc(row["exit_time_utc"]), where
            assert mine.exit_price == D(row["exit_price"]), where


def test_every_slice_books_tradingviews_pnl_to_the_cent(replay):
    """TradingView lists PnL in cents, so a cent either way is its rounding —
    plus the seed's two ten-thousandths of a lot (see the entry-size test),
    which the final slice of a campaign carries across the whole move."""
    ours, theirs = replay
    for mine, row in zip(ours, theirs, strict=True):
        if int(row["trade"]) >= FIRST_EXACT_TRADE and row["exit_time_utc"]:
            move = abs(mine.exit_price - mine.entry_price)
            allowed = D("0.01") + D("0.0002") * move
            assert abs(mine.pnl - D(row["pnl_usdc"])) <= allowed, f"trade {row['trade']}"


def test_every_entry_is_the_size_tradingview_printed_on_the_chart(replay):
    """Two ten-thousandths is the cent rounding of the 39 PnL figures the seed is summed from."""
    ours, _ = replay
    sizes: dict[int, Decimal] = {}
    for mine in ours:
        sizes[mine.entry_time] = sizes.get(mine.entry_time, D(0)) + mine.qty
    for when, label in CHART_LABELS.items():
        assert abs(sizes[utc(when)] - label) <= D("0.0002"), when


def test_the_venues_filler_bars_are_in_the_fixture_and_not_in_the_replay():
    """33 quiet slots Hyperliquid serves as flat zero-volume candles. Replayed,
    they moved the 2026-08-11 reversal from 06:00 to 05:30."""
    fillers = [bar for bar in _bars() if bar.volume == 0 and bar.high == bar.low]
    assert len(fillers) == 33
