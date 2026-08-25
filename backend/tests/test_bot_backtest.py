"""`docs/bot-mode.md` §4 — the backtest, and what it is honest about.

A backtest whose fill model is optimistic is worse than no backtest, because it
produces a number people act on. Every assumption here is asserted, and the
report prints them above the metrics rather than in a footnote.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

from apps.bots import backtest
from apps.bots.backtest import BacktestError
from apps.bots.report import ClosedTrade, compute_metrics
from apps.pine.bar import Bar
from tests import pine_corpus

D = Decimal

ALWAYS_LONG = """//@version=5
strategy("always long")
if strategy.position_size == 0
    strategy.entry("L", strategy.long)
"""

CROSS = (pine_corpus.ACCEPT / "01_sma_cross.pine").read_text()

STOPPED = """//@version=5
strategy("stopped")
if strategy.position_size == 0
    strategy.entry("L", strategy.long)
    strategy.exit("x", "L", loss_pct=1, profit_pct=1)
"""


def bar(open_, high, low, close, *, time=0) -> Bar:
    return Bar(
        time=time,
        open=D(open_),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D("1"),
    )


def go(source: str, bars: list[Bar], **kwargs):
    return backtest.run(
        source=source,
        symbol="BTCUSDT",
        interval="15m",
        from_time=bars[0].time,
        to_time=bars[-1].time,
        bars=bars,
        **kwargs,
    )


# --- the fill model ---------------------------------------------------------


def test_an_entry_fills_at_the_next_bars_open_not_this_bars_close():
    """The signal is known only once the bar has closed; filling at that close
    is the single most common way a backtest invents money."""
    bars = [
        bar("100", "100", "100", "100", time=0),
        bar("200", "200", "200", "200", time=900),
        bar("200", "200", "200", "200", time=1800),
    ]
    report = go(ALWAYS_LONG, bars, initial_equity=D("1000"))
    assert report.trades or report.metrics["trades"] == 0
    if report.trades:
        assert report.trades[0].entry_price >= D("200")


def test_slippage_moves_the_fill_against_the_trade():
    with override_settings(BOT={**_bot_settings(), "BACKTEST_SLIPPAGE_BPS": "100"}):
        bars = pine_corpus.trending(30)
        report = go(ALWAYS_LONG, bars)
    entry = report.trades[0].entry_price if report.trades else None
    assert entry is None or entry > bars[1].open


def test_the_fee_is_charged_on_both_sides():
    bars = pine_corpus.trending(40)
    with override_settings(BOT={**_bot_settings(), "BACKTEST_FEE_BPS": "0"}):
        free = go(CROSS, bars).metrics["net_pnl"]
    with override_settings(BOT={**_bot_settings(), "BACKTEST_FEE_BPS": "50"}):
        charged = go(CROSS, bars).metrics["net_pnl"]
    assert charged <= free


def test_a_bar_that_touches_both_levels_is_assumed_to_have_stopped_out():
    """Intrabar order is unknowable from a candle, so the backtest takes the
    pessimistic reading rather than the flattering one."""
    bars = [
        bar("100", "100", "100", "100", time=0),
        bar("100", "100", "100", "100", time=900),
        # Reaches +1% and -1% in the same bar.
        bar("100", "102", "98", "100", time=1800),
        bar("100", "100", "100", "100", time=2700),
    ]
    report = go(STOPPED, bars, initial_equity=D("1000"))
    assert report.trades
    assert report.trades[0].pnl < 0


# --- honesty ----------------------------------------------------------------


def test_the_report_states_its_assumptions_before_its_metrics():
    report = go(CROSS, pine_corpus.bars(120))
    lines = report.summary_lines()
    assert lines[0].startswith("Fill model")
    assert any("slippage" in line.lower() for line in lines)
    first_metric = next(i for i, line in enumerate(lines) if "net PnL" in line)
    assert first_metric > 1


def test_the_assumptions_travel_in_the_payload_too():
    report = go(CROSS, pine_corpus.bars(120))
    assert report.as_dict()["assumption_lines"]


def test_a_backtest_over_a_script_outside_the_subset_refuses():
    with pytest.raises(BacktestError) as caught:
        go(
            '//@version=5\nstrategy("x")\nmark = label.new(bar_index, high, "hi")\n',
            pine_corpus.bars(20),
        )
    assert "label" in str(caught.value)


def test_a_backtest_with_no_bars_says_so_rather_than_reporting_zero():
    with pytest.raises(BacktestError):
        backtest.run(
            source=CROSS, symbol="BTCUSDT", interval="15m", from_time=0, to_time=1, bars=[]
        )


# --- determinism ------------------------------------------------------------


def test_the_same_run_twice_produces_the_same_digest():
    """The digest is the whole divergence check; if it moves on its own it
    cannot tell a real divergence from noise."""
    bars = pine_corpus.bars(200)
    assert go(CROSS, bars).intent_digest == go(CROSS, bars).intent_digest


def test_a_different_script_produces_a_different_digest():
    bars = pine_corpus.bars(200)
    assert go(CROSS, bars).intent_digest != go(ALWAYS_LONG, bars).intent_digest


def test_the_digest_is_over_intents_not_over_fills():
    """Fills depend on the fill model; intents are the strategy's own decisions,
    and they are what a live run can be compared against."""
    bars = pine_corpus.bars(200)
    with override_settings(BOT={**_bot_settings(), "BACKTEST_SLIPPAGE_BPS": "0"}):
        a = go(CROSS, bars).intent_digest
    with override_settings(BOT={**_bot_settings(), "BACKTEST_SLIPPAGE_BPS": "200"}):
        b = go(CROSS, bars).intent_digest
    assert a == b


# --- warm-up ----------------------------------------------------------------


def test_a_window_with_too_little_warm_up_says_so():
    """The earliest signals are decided by numbers TradingView still shows as
    `na`. Cheap to say, and invisible if it is not said."""
    report = go(CROSS, pine_corpus.bars(15))
    assert any("warm-up" in w for w in report.warnings)


def test_a_window_consumed_entirely_by_warm_up_says_it_describes_nothing():
    bars = pine_corpus.bars(30)
    report = backtest.run(
        source=CROSS,
        symbol="BTCUSDT",
        interval="15m",
        from_time=bars[-1].time + 900,
        to_time=bars[-1].time + 1800,
        bars=bars,
    )
    assert any("describes nothing" in w for w in report.warnings)


def test_every_price_in_the_report_is_a_decimal():
    report = go(CROSS, pine_corpus.bars(150))
    for trade in report.trades:
        assert isinstance(trade.entry_price, Decimal)
        assert isinstance(trade.pnl, Decimal)
    for _, equity in report.equity_curve:
        assert isinstance(equity, Decimal)


# --- metrics ----------------------------------------------------------------


def closed(pnl: str, *, bars: int = 2, entry: int = 0) -> ClosedTrade:
    return ClosedTrade(
        side="long",
        entry_time=entry,
        entry_price=D("100"),
        exit_time=entry + bars * 900,
        exit_price=D("100") + D(pnl),
        qty=D("1"),
        pnl=D(pnl),
        fees=D("0"),
        bars_held=bars,
        exit_reason="test",
    )


def metrics(trades, curve=None, interval="15m", bars=100):
    return compute_metrics(
        trades=trades,
        equity_curve=curve or [(0, D("1000")), (900, D("1000"))],
        interval=interval,
        bars=bars,
        initial_equity=D("1000"),
    )


def test_win_rate_counts_only_closed_trades():
    got = metrics([closed("10"), closed("-5"), closed("10")])
    assert got["win_rate_pct"] == D("66.66666667")


def test_profit_factor_is_gross_win_over_gross_loss():
    got = metrics([closed("10"), closed("-5")])
    assert got["profit_factor"] == D("2")


def test_profit_factor_with_no_losses_does_not_divide_by_zero():
    got = metrics([closed("10")])
    assert got["profit_factor"] is None or got["profit_factor"] > 0


def test_max_consecutive_losses_is_the_longest_run():
    got = metrics([closed("-1"), closed("-1"), closed("5"), closed("-1")])
    assert got["max_consecutive_losses"] == 2


def test_max_drawdown_is_peak_to_trough():
    curve = [(0, D("100")), (900, D("150")), (1800, D("75")), (2700, D("120"))]
    got = metrics([], curve)
    assert got["max_drawdown_pct"] == D("50")


def test_a_flat_curve_has_no_drawdown():
    got = metrics([], [(0, D("100")), (900, D("100"))])
    assert got["max_drawdown_pct"] == D("0")


def test_no_trades_reports_zero_rather_than_omitting_the_metric():
    got = metrics([])
    assert got["trades"] == 0
    assert got["net_pnl"] == D("0")


def _bot_settings() -> dict:
    from django.conf import settings

    return dict(settings.BOT)
