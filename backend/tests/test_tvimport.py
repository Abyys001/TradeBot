"""The TradingView importer, checked against the export the parity fixture was made from.

The point of the test is not that a CSV parses. It is that
`list_of_trades.csv` — which a parity test then treats as the truth about the
engine — is **reproducible** from the raw export beside it, clock included. A
conversion nobody can redo is a second source of truth.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from apps.bots import tvimport
from apps.pine.bar import Bar

D = Decimal
HERE = Path(__file__).parent / "fixtures" / "pine" / "tradingview" / "mcg_t3_flow_perp"
RAW = HERE / "list_of_trades.tradingview.csv"


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


def _raw() -> str:
    return RAW.read_text(encoding="utf-8-sig")


def test_the_two_rows_tradingview_prints_per_trade_become_one():
    trades = tvimport.parse(_raw())
    assert len(trades) == 86
    first = trades[0]
    assert (first.side, first.signal) == ("short", "Short TP1")
    assert first.entry_price == D("484.9498")
    assert first.exit_price == D("454.2902")
    assert first.qty == D("0.0618")
    assert first.pnl == D("1.87")


def test_the_position_still_open_at_the_end_survives_the_import():
    """It has no exit and an em dash where its price would be. Dropping it
    would drop the only record of the entry TradingView made last."""
    last = tvimport.parse(_raw())[-1]
    assert last.trade == 86
    assert last.exit_time is None and last.exit_price is None
    assert last.entry_price == D("1106.2998")
    assert last.qty == D("0.2851")


def test_the_charts_timezone_is_read_off_the_prices():
    """Nothing in the export says +03:30; every fill price being a bar's close
    at that offset, and at no other, is what says it."""
    assert tvimport.chart_offset(tvimport.parse(_raw()), _bars()) == 3 * 3600 + 1800


def test_the_committed_fixture_is_what_the_importer_produces():
    trades = tvimport.parse(_raw())
    offset = tvimport.chart_offset(trades, _bars())
    assert (
        tvimport.fixture_csv(tvimport.shift(trades, offset))
        == (HERE / "list_of_trades.csv").read_text()
    )


def test_bars_from_the_wrong_market_are_refused_rather_than_aligned():
    """The failure this guards is silent: bars of the right shape and the wrong
    instrument would align on *some* offset and blame the engine for the rest."""
    bars = [
        Bar(
            time=bar.time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close * 2,
            volume=bar.volume,
        )
        for bar in _bars()
    ]
    with pytest.raises(tvimport.TradingViewImportError):
        tvimport.chart_offset(tvimport.parse(_raw()), bars)


def test_an_export_that_is_not_a_list_of_trades_says_so():
    with pytest.raises(tvimport.TradingViewImportError) as caught:
        tvimport.parse("Date,Equity\n2026-01-01,100\n")
    assert "List of Trades" in str(caught.value)
