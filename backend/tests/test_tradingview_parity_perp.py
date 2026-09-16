"""A second TradingView run, replayed bar for bar — this time the instrument the bot trades.

McGinley T3 Flow Campaign on the Hyperliquid **perpetual** ZEC/USDC, 30m, the
Properties tab the admin ran it with: 100 USDC of capital, 100% of equity per
entry, commission 0.05%, and **slippage 2 ticks** — the three things the spot
fixture next door does not exercise. Everything compounds off a hundred
dollars, so a sizing error of a cent in June is a sizing error of a dollar in
September and cannot hide.

Provenance and what could not be replayed are in the fixture's README. The
short version: Hyperliquid serves the latest 5000 bars, which is 104 days at
30m, so 60 of TradingView's 86 trades are older than any bar this venue will
still sell. The replay starts on the reversal of 2026-06-19 04:00 — the first
bar inside that history on which TradingView both closed a campaign and opened
one, so the engine, which starts flat, starts where TradingView starts too, on
TradingView's own equity.
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
HERE = Path(__file__).parent / "fixtures" / "pine" / "tradingview" / "mcg_t3_flow_perp"
SOURCE = (pine_corpus.ACCEPT / "27_published_strategy.pine").read_text()
#: TradingView's reversal bar: trade 64 closes on it and trade 65 opens on it.
WINDOW_FROM = "2026-06-19 04:00"
#: TradingView's own mintick for HYPERLIQUID:ZECUSDC.P, which is what the
#: Properties tab's "2 ticks" of slippage is counted in. The venue quotes to
#: five significant figures, so its tick is not this and a backtest that reads
#: the listing instead would slip a hundred times too far.
MINTICK = D("0.0001")
INITIAL_CAPITAL = D(100)


def utc(text: str) -> int:
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())


def _bars() -> list[Bar]:
    with open(HERE / "bars_hl_perp_zec_30m.csv") as fh:
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
    # TradingView's equity on the bar the replay starts on: everything it had
    # closed by then, including the campaign it closes on this very bar.
    equity = INITIAL_CAPITAL + sum(
        D(row["pnl_usdc"])
        for row in tv
        if row["exit_time_utc"] and utc(row["exit_time_utc"]) <= start
    )
    bars = _bars()
    report = backtest.run(
        source=SOURCE,
        symbol="ZECUSDC",
        interval="30m",
        from_time=start,
        to_time=bars[-1].time,
        bars=bars,
        mintick=MINTICK,
        price_tick=MINTICK,
        qty_step=D("0.0001"),
        property_overrides={
            "initial_capital": equity,
            "default_qty_value": D(100),
            "pyramiding": 1,
            "slippage": 2,
        },
    )
    theirs = [row for row in tv if utc(row["entry_time_utc"]) >= start]
    return report.trades, theirs


def test_every_trade_opens_and_closes_on_the_bar_and_at_the_price_tradingview_did(replay):
    """21 closed trades and the one still open when the admin exported the list.

    The engine keeps running past the export, so its list is longer; the trades
    TradingView recorded are its first 22, in order.
    """
    ours, theirs = replay
    assert len(theirs) == 22
    closed = [row for row in theirs if row["exit_time_utc"]]
    assert len(closed) == 21
    for mine, row in zip(ours, closed, strict=False):
        where = f"trade {row['trade']} ({row['signal']})"
        assert mine.side == row["side"], where
        assert mine.entry_time == utc(row["entry_time_utc"]), where
        assert mine.entry_price == D(row["entry_price"]), where
        assert mine.exit_time == utc(row["exit_time_utc"]), where
        assert mine.exit_price == D(row["exit_price"]), where


def test_every_slice_books_tradingviews_pnl_to_the_cent(replay):
    """TradingView prints PnL in cents, so a cent either way is its own rounding."""
    ours, theirs = replay
    closed = [row for row in theirs if row["exit_time_utc"]]
    for mine, row in zip(ours, closed, strict=False):
        assert abs(mine.pnl - D(row["pnl_usdc"])) <= D("0.01"), f"trade {row['trade']}"


def test_every_entry_is_the_size_tradingview_sized_it(replay):
    """100% of equity compounding from 100 USDC: the sizes are the equity curve.

    A lot either way is the quantity step — TradingView rounds to four decimals
    here and so does the replay, from an equity that is itself a sum of figures
    TradingView printed to the cent.
    """
    ours, theirs = replay
    closed = [row for row in theirs if row["exit_time_utc"]]
    for mine, row in zip(ours, closed, strict=False):
        assert abs(mine.qty - D(row["qty"])) <= D("0.0001"), f"trade {row['trade']}"


def test_the_trade_still_open_when_the_list_was_exported_was_entered_the_same_way(replay):
    """TradingView's last row is a position, not a result: it has no exit.

    The engine went on to scale it out, so its size is checked against the sum
    of the slices that came from it rather than against one of them.
    """
    ours, theirs = replay
    still_open = [row for row in theirs if not row["exit_time_utc"]]
    assert len(still_open) == 1
    row = still_open[0]
    when = utc(row["entry_time_utc"])
    mine = [trade for trade in ours if trade.entry_time == when]
    assert mine, "the replay never opened TradingView's last position"
    assert {trade.side for trade in mine} == {row["side"]}
    assert all(trade.entry_price == D(row["entry_price"]) for trade in mine)
    assert abs(sum(trade.qty for trade in mine) - D(row["qty"])) <= D("0.0001")


def test_the_two_ticks_of_slippage_are_in_every_fill(replay):
    """Properties → Slippage, in TradingView's unit and against its mintick.

    Every fill is `process_orders_on_close`'s bar close, moved two ten-thousandths
    against the side that is trading. It is asserted on the fills rather than on
    the report header because a header can say 2 while nothing moves.
    """
    ours, _ = replay
    closes = {bar.time: bar.close for bar in _bars()}
    for trade in ours:
        buy_to_open = trade.side == "long"
        entry = closes[trade.entry_time] + (2 * MINTICK if buy_to_open else -2 * MINTICK)
        assert trade.entry_price == entry, f"entry {trade.entry_time}"
        if trade.exit_reason == "end of window":
            # Not a fill: the replay ran out of bars while the position was
            # open, and marks it at the last close. TradingView does not close
            # it at all — its own last row has no exit either.
            assert trade.exit_price == closes[trade.exit_time]
            continue
        leaving = closes[trade.exit_time] + (-2 * MINTICK if buy_to_open else 2 * MINTICK)
        assert trade.exit_price == leaving, f"exit {trade.exit_time}"


def test_the_venue_no_longer_sells_the_bars_most_of_this_year_happened_on():
    """The gap is a recorded fact, not an omission — see the fixture's README.

    Hyperliquid serves the latest 5000 bars; the archive is what will one day
    make the other 60 trades replayable, so this number is expected to *fall*.
    """
    bars = _bars()
    tv = _tradingview()
    unreachable = [row for row in tv if utc(row["entry_time_utc"]) < bars[0].time]
    assert len(tv) == 86
    assert len(unreachable) == 60


def test_the_equity_curve_arrives_where_tradingviews_did(replay):
    """Trade by trade is the strong claim; this is the one the Key stats show.

    TradingView's cumulative PnL column runs 69.71 → 215.51 across these 21
    trades. The replay is allowed the cent per trade that its own rounding is
    worth, and nothing more — a compounding error would not stay inside it.
    """
    ours, theirs = replay
    closed = [row for row in theirs if row["exit_time_utc"]]
    booked = sum(mine.pnl for mine in ours[: len(closed)])
    printed = sum(D(row["pnl_usdc"]) for row in closed)
    assert printed == D("145.80")  # 215.51 - 69.71, off its own cumulative column
    assert abs(booked - printed) <= D("0.01") * len(closed)
