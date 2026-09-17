"""The live loop and the backtest must converge the same indicators.

This is the test for a bug that had no error message. A bot entered a long on
the Hyperliquid ZEC perpetual and then held it for thirty-three bars while the
same script, replayed over the same archive, had entered four hours earlier and
scaled out on the bar after. Nothing had failed: the supervisor was warming the
runtime on ``max(20, ta_call_sites * 10)`` bars — the *number* of ``ta.*`` call
sites, multiplied by ten — where the backtest warmed it on the longest period
those calls were actually made with. For a script whose deepest indicator is
``ta.atr(200)`` that is 300 bars against 600, and an ``rma`` seeded 300 bars ago
is not the same number as one seeded 600 bars ago. So the live bot was trading a
strategy that had never been backtested: it entered where the report was flat,
and the reversal that was supposed to close the position never fired.

The fix is that there is now one function. These tests are what stops there
being two again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.bots.feed import longest_lookback, strategy_warmup, warmup_bars_needed
from apps.pine.validate import validate

CORPUS = Path(__file__).parent / "fixtures" / "pine" / "accept"
PUBLISHED = CORPUS / "27_published_strategy.pine"


def test_the_backtest_and_the_live_loop_ask_for_the_same_number_of_bars():
    """Read off the two call sites rather than asserted as a constant.

    A number copied into this test would go stale the moment one side changed;
    the claim is that the *sources* agree, so the sources are what is compared.
    """
    supervisor = (Path("apps") / "bots" / "supervisor.py").read_text()
    backtest = (Path("apps") / "bots" / "backtest.py").read_text()
    assert "strategy_warmup(result, bot.input_values or {})" in supervisor
    assert "strategy_warmup(result, inputs or {})" in backtest
    # And the live loop no longer asks for a *period* it would multiply out
    # itself, which is the shape the old guess came in.
    assert "warmup(lookback=" not in supervisor


def test_the_published_strategy_needs_its_deepest_indicator_not_its_call_count():
    """`ta.atr(200)` is the deepest; the old rule never saw it."""
    result = validate(PUBLISHED.read_text())
    assert result.ok, result.errors
    assert longest_lookback(result) == 200
    assert strategy_warmup(result) == 600
    # What the supervisor used to compute, kept here as the thing being fixed:
    # ten call sites, times ten, floored at the minimum.
    assert warmup_bars_needed(result.ta_call_sites * 10) == 300


def test_a_length_the_operator_raised_is_a_length_the_warm_up_covers():
    """A period that lives in the bot's inputs is in no literal in the source.

    ``McGinley Length`` defaults to 65. An operator who sets it to 400 has a
    script whose deepest indicator is 400 bars deep and whose source still says
    65 everywhere — so a warm-up read off the AST alone would converge nothing
    and there would be no sign of it.
    """
    source = """//@version=5
strategy("x")
length = input.int(20, "Length")
plot(ta.sma(close, length))
"""
    result = validate(source)
    assert strategy_warmup(result) == 300  # the floor: 20 * 3 is under it
    assert strategy_warmup(result, {"length": 400}) == 1200


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.pine")), ids=lambda p: p.name)
def test_every_accepted_script_gets_a_warm_up_it_could_actually_converge_on(path):
    """No script in the corpus asks for less warm-up than its own longest period."""
    result = validate(path.read_text())
    if not result.ok:
        pytest.skip("not an accepted script under the current subset")
    assert strategy_warmup(result) >= longest_lookback(result)


# --- the same claim against real bars ---------------------------------------
#
# The tests above compare two numbers. These compare two *runs*, on the venue's
# own ZEC perpetual bars — the fixture the TradingView parity tests replay — and
# are what turns "300 is not 600" into "300 traded a different strategy".


def _fixture_bars():
    import csv
    from decimal import Decimal

    from apps.pine.bar import Bar

    path = (
        Path(__file__).parent
        / "fixtures"
        / "pine"
        / "tradingview"
        / "mcg_t3_flow_perp"
        / "bars_hl_perp_zec_30m.csv"
    )
    with open(path) as fh:
        return [
            Bar(
                time=int(row["time"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=Decimal(row["volume"]),
            )
            for row in csv.DictReader(fh)
        ]


def _intents(bars, *, warmup: int, tail: int):
    """Replay the last ``tail`` bars after ``warmup`` bars of convergence.

    A hand-rolled driver rather than the backtest engine, because what is being
    compared is the *runtime's* output — the intent — not a fill model. It does
    the one thing both real drivers do: tell the runtime what is held before
    each bar (`sync_position`), so the comparison is like for like.
    """
    from decimal import Decimal

    from apps.bots.config import limits
    from apps.pine.runtime import Runtime
    from apps.pine.symbol import SymbolInfo, TimeframeInfo

    result = validate(PUBLISHED.read_text())
    runtime = Runtime(
        result.program,
        symbol="ZECUSDC",
        limits=limits(),
        symbol_info=SymbolInfo.for_symbol(
            "ZECUSDC", market="futures", mintick=Decimal("0.0001")
        ),
        timeframe=TimeframeInfo.for_interval("30m"),
    )
    window = bars[-(warmup + tail):]
    start = bars[-tail].time
    held, fraction, avg = 0, Decimal(1), None
    out = []
    for bar in window:
        runtime.sync_position(
            size_sign=held,
            avg_price=avg,
            equity=Decimal(100),
            opentrades=0 if held == 0 else 1,
            performance={},
            fraction=fraction,
        )
        intent = runtime.run_bar(bar, ishistory=bar.time < start).intent
        if bar.time >= start:
            out.append(
                (
                    bar.time,
                    intent.desired_side.value if intent.desired_side else None,
                    str(intent.position_fraction),
                )
            )
        wanted = (
            0
            if intent.desired_side is None
            else (1 if intent.desired_side.value == "long" else -1)
        )
        if wanted != held:
            avg, fraction = bar.close, Decimal(1)
        else:
            fraction = intent.position_fraction
        held = wanted
    return out


TAIL = 200


def test_the_shared_warm_up_reproduces_a_full_history_replay_bar_for_bar():
    """600 bars is enough; the whole archive changes nothing. That is the claim."""
    bars = _fixture_bars()
    assert _intents(bars, warmup=600, tail=TAIL) == _intents(bars, warmup=4000, tail=TAIL)


def test_the_old_live_warm_up_traded_a_different_strategy_on_these_same_bars():
    """300 bars is not a slightly less precise answer — it is another strategy.

    On these 200 bars it holds a whole short for the entire window, having
    missed the TP1 the converged run takes off it. Nothing errors, nothing is
    logged, and the position simply behaves differently from every report ever
    run on it. This test is here so that the number can never quietly go back.
    """
    bars = _fixture_bars()
    converged = _intents(bars, warmup=600, tail=TAIL)
    unconverged = _intents(bars, warmup=300, tail=TAIL)
    differing = [
        (mine, theirs)
        for mine, theirs in zip(unconverged, converged, strict=True)
        if mine != theirs
    ]
    assert len(differing) > TAIL // 2, "the two agreed — pick a window where they do not"
    # And the difference is a real one about the position, not a rounding digit.
    assert {row[0][2] for row in differing} == {"1"}
    assert {row[1][2] for row in differing} == {"0.70"}
