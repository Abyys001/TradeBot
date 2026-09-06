"""`docs/bot-plan.md` §4 — the indicators.

The oracles here are naive transcriptions of the code examples in
`reference/pinescriptv6/reference/functions/ta.md`: recompute the whole window
from scratch on every bar, the way the reference writes the formula, and compare
against the O(1) incremental implementation. That pins the incremental form
against the textbook one.

It is deliberately **not** what Q29 asks for. An oracle written from the same
reference the implementation was written from cannot catch a misreading of that
reference — only an export from TradingView can, and Q29 is the open question of
who produces it. `test_the_exported_golden_values` runs the moment one appears
in `fixtures/pine/golden/`.
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal, localcontext

import pytest

from apps.pine import ta
from apps.pine.bar import Bar
from apps.pine.errors import PineRuntimeError
from apps.pine.limits import DEFAULT_LIMITS
from apps.pine.runtime import RunContext
from apps.pine.series import NA, is_na
from tests import pine_corpus


@pytest.fixture(autouse=True)
def _wide_precision():
    """The golden values carry more digits than the default 28-digit context.

    Set on the global context this leaked out of the module: ``getcontext()``
    is process-wide, and pytest imports every test module before it runs any of
    them, so one assignment here widened the context for the entire session.
    ``test_ledger.py`` asserts an exact 28-digit quotient and failed because of
    a line in a file it never imports. ``localcontext`` scopes the widening to
    the test that wants it.
    """
    with localcontext() as ctx:
        ctx.prec = 34
        yield


GOLDEN = pine_corpus.FIXTURES / "golden"
TOLERANCE = Decimal("0.00000001")


def context(bars: list[Bar]) -> RunContext:
    """A context whose built-in series have been fed `bars`, as the runtime does."""
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    return ctx


def feed(indicator: ta.Indicator, bars: list[Bar], *args, source: str = "close") -> list:
    """Run `indicator` over `bars`, returning one value per bar."""
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    out = []
    for index, bar in enumerate(bars):
        ctx.bar = bar
        ctx.bar_index = index
        for name in ("open", "high", "low", "close", "volume"):
            ctx.series[name].push(getattr(bar, name))
        ctx.series["hl2"].push((bar.high + bar.low) / 2)
        ctx.series["hlc3"].push((bar.high + bar.low + bar.close) / 3)
        ctx.series["ohlc4"].push((bar.open + bar.high + bar.low + bar.close) / 4)
        value = getattr(bar, source) if source != "none" else None
        out.append(indicator.update(ctx, *( (value,) + args if source != "none" else args)))
    return out


def close_of(bars: list[Bar]) -> list[Decimal]:
    return [b.close for b in bars]


def near(a, b, tolerance: Decimal = TOLERANCE) -> bool:
    if is_na(a) or is_na(b):
        return is_na(a) and is_na(b)
    return abs(Decimal(a) - Decimal(b)) <= tolerance


BARS = pine_corpus.bars(120)
CLOSES = close_of(BARS)


# --- naive oracles, transcribed from the reference --------------------------


def naive_sma(values: list[Decimal], length: int) -> list:
    out = []
    for index in range(len(values)):
        if index + 1 < length:
            out.append(NA)
        else:
            window = values[index + 1 - length : index + 1]
            out.append(sum(window, Decimal(0)) / Decimal(length))
    return out


def naive_rma(values: list[Decimal], length: int) -> list:
    """`pine_rma`: seeded with the SMA, then alpha = 1/length."""
    alpha = Decimal(1) / Decimal(length)
    seed = naive_sma(values, length)
    out: list = []
    running = NA
    for index in range(len(values)):
        if is_na(running):
            running = seed[index]
        else:
            running = alpha * values[index] + (Decimal(1) - alpha) * running
        out.append(running)
    return out


def naive_stdev(values: list[Decimal], length: int) -> list:
    """`pine_stdev`: biased — divided by `length`, not `length - 1`."""
    out = []
    means = naive_sma(values, length)
    for index in range(len(values)):
        if is_na(means[index]):
            out.append(NA)
            continue
        window = values[index + 1 - length : index + 1]
        mean = means[index]
        total = sum(((item - mean) ** 2 for item in window), Decimal(0))
        out.append((total / Decimal(length)).sqrt())
    return out


def naive_ema(values: list[Decimal], length: int) -> list:
    alpha = Decimal(2) / Decimal(length + 1)
    seed = naive_sma(values, length)
    out: list = []
    running = NA
    for index in range(len(values)):
        if is_na(running):
            running = seed[index]
        else:
            running = alpha * values[index] + (Decimal(1) - alpha) * running
        out.append(running)
    return out


def naive_rsi(values: list[Decimal], length: int) -> list:
    """`pine_rsi`: rma of upward and downward change."""
    ups = [Decimal(0)]
    downs = [Decimal(0)]
    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        ups.append(max(change, Decimal(0)))
        downs.append(max(-change, Decimal(0)))
    up_rma = naive_rma(ups[1:], length)
    down_rma = naive_rma(downs[1:], length)
    out: list = [NA]
    for up, down in zip(up_rma, down_rma, strict=True):
        if is_na(up) or is_na(down):
            out.append(NA)
        elif down == 0:
            out.append(Decimal(100))
        else:
            rs = up / down
            out.append(Decimal(100) - Decimal(100) / (Decimal(1) + rs))
    return out


def naive_true_range(bars: list[Bar]) -> list[Decimal]:
    """`pine_atr`'s trueRange: `high - low` on the first bar."""
    out = []
    for index, bar in enumerate(bars):
        if index == 0:
            out.append(bar.high - bar.low)
        else:
            previous = bars[index - 1].close
            out.append(
                max(bar.high - bar.low, abs(bar.high - previous), abs(bar.low - previous))
            )
    return out


# --- the comparisons --------------------------------------------------------


@pytest.mark.parametrize("length", [2, 5, 14, 50])
def test_sma_matches_the_naive_window(length):
    got = feed(ta.SMA(), BARS, length)
    assert all(near(a, b) for a, b in zip(got, naive_sma(CLOSES, length), strict=True))


@pytest.mark.parametrize("length", [5, 14, 21])
def test_ema_matches_the_naive_recurrence(length):
    got = feed(ta.EMA(), BARS, length)
    assert all(near(a, b) for a, b in zip(got, naive_ema(CLOSES, length), strict=True))


@pytest.mark.parametrize("length", [5, 14])
def test_rma_matches_the_reference_seeding(length):
    """The Q29 trap: an rma seeded with the first value, not the SMA, is wrong forever."""
    got = feed(ta.RMA(), BARS, length)
    assert all(near(a, b) for a, b in zip(got, naive_rma(CLOSES, length), strict=True))


def test_rma_seeds_with_the_simple_average_of_the_first_window():
    got = feed(ta.RMA(), BARS, 10)
    assert near(got[9], sum(CLOSES[:10], Decimal(0)) / Decimal(10))


def test_an_rma_seeded_from_the_first_value_would_disagree():
    """Proof the seeding assertion above has teeth rather than passing vacuously."""
    alpha = Decimal(1) / Decimal(10)
    wrong = CLOSES[0]
    for value in CLOSES[1:10]:
        wrong = alpha * value + (Decimal(1) - alpha) * wrong
    correct = feed(ta.RMA(), BARS, 10)[9]
    assert not near(wrong, correct)


@pytest.mark.parametrize("length", [7, 14])
def test_rsi_matches_the_reference_formula(length):
    got = feed(ta.RSI(), BARS, length)
    want = naive_rsi(CLOSES, length)
    assert all(near(a, b, Decimal("0.0000001")) for a, b in zip(got, want, strict=True))


def test_rsi_stays_inside_zero_and_one_hundred():
    for value in feed(ta.RSI(), BARS, 14):
        if not is_na(value):
            assert Decimal(0) <= value <= Decimal(100)


@pytest.mark.parametrize("length", [5, 20])
def test_stdev_is_biased_like_tradingviews_default(length):
    got = feed(ta.Stdev(), BARS, length)
    want = naive_stdev(CLOSES, length)
    assert all(near(a, b, Decimal("0.000001")) for a, b in zip(got, want, strict=True))


def test_variance_is_stdev_squared():
    var = feed(ta.Variance(), BARS, 10)
    dev = feed(ta.Stdev(), BARS, 10)
    for v, d in zip(var, dev, strict=True):
        if not is_na(v):
            assert near(v, d * d, Decimal("0.000001"))


def test_true_range_is_na_on_the_first_bar_by_default():
    assert is_na(feed(ta.TrueRange(), BARS, source="none")[0])


def test_true_range_with_handle_na_uses_high_minus_low():
    got = feed(ta.TrueRange(), BARS, True, source="none")
    assert near(got[0], BARS[0].high - BARS[0].low)


def test_atr_is_the_rma_of_true_range_including_the_first_bar():
    """`ta.atr` uses `ta.tr(true)`, which is why it has a value where `ta.tr` does not."""
    got = feed(ta.ATR(), BARS, 14, source="none")
    want = naive_rma(naive_true_range(BARS), 14)
    assert all(near(a, b, Decimal("0.0000001")) for a, b in zip(got, want, strict=True))


# --- warm-up ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "args"),
    [
        (ta.SMA, (20,)),
        (ta.EMA, (20,)),
        (ta.RMA, (20,)),
        (ta.WMA, (20,)),
        (ta.Stdev, (20,)),
        (ta.Variance, (20,)),
    ],
)
def test_an_indicator_is_na_until_its_window_fills(factory, args):
    """Never a partial answer — a half-filled average is a different indicator."""
    got = feed(factory(), BARS, *args)
    assert all(is_na(v) for v in got[: args[0] - 1])
    assert not is_na(got[args[0] - 1])


def test_highest_and_lowest_bracket_the_window():
    highs = feed(ta.Highest(), BARS, 10)
    lows = feed(ta.Lowest(), BARS, 10)
    for index in range(9, len(BARS)):
        window = CLOSES[index - 9 : index + 1]
        assert highs[index] == max(window)
        assert lows[index] == min(window)


def test_highestbars_counts_back_to_the_extreme():
    bars_back = feed(ta.HighestBars(), BARS, 10)
    for index in range(9, len(BARS)):
        window = CLOSES[index - 9 : index + 1]
        offset = bars_back[index]
        assert CLOSES[index + int(offset)] == max(window)


# --- the rest of the subset, for shape rather than value --------------------


@pytest.mark.parametrize(
    ("factory", "args"),
    [
        (ta.WMA, (10,)),
        (ta.VWMA, (10,)),
        (ta.HMA, (10,)),
        (ta.ROC, (10,)),
        (ta.Change, (1,)),
        (ta.CCI, (20,)),
        (ta.Cum, ()),
        (ta.Sum, (10,)),
        (ta.LinReg, (20, 0)),
        (ta.PercentileLinearInterpolation, (20, 50)),
        (ta.Rising, (5,)),
        (ta.Falling, (5,)),
    ],
)
def test_every_indicator_runs_a_full_series_without_raising(factory, args):
    got = feed(factory(), BARS, *args)
    assert len(got) == len(BARS)


def test_macd_returns_three_series():
    values = feed(ta.MACD(), BARS, 12, 26, 9)
    assert len(values[-1]) == 3


def test_bollinger_bands_are_ordered():
    mid, upper, lower = feed(ta.BollingerBands(), BARS, 20, 2)[-1]
    assert lower < mid < upper


def test_bbw_is_the_band_width_over_the_basis():
    mid, upper, lower = feed(ta.BollingerBands(), BARS, 20, 2)[-1]
    width = feed(ta.BBW(), BARS, 20, 2)[-1]
    assert near(width, (upper - lower) / mid, Decimal("0.000001"))


def test_crossover_fires_once_on_the_crossing_bar():
    rising = pine_corpus.trending(20)
    crossing = ta.Crossover()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    fired = [crossing.update(ctx, bar.close, Decimal("105")) for bar in rising]
    assert fired.count(True) == 1


def test_crossunder_is_the_mirror():
    falling = list(reversed(pine_corpus.trending(20)))
    crossing = ta.Crossunder()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    fired = [crossing.update(ctx, bar.close, Decimal("105")) for bar in falling]
    assert fired.count(True) == 1


def test_barssince_counts_from_the_last_true():
    since = ta.BarsSince()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    got = [since.update(ctx, flag) for flag in [False, True, False, False, True, False]]
    assert got[-1] == 1
    assert got[3] == 2


def test_valuewhen_reads_the_source_at_the_nth_most_recent_occurrence():
    when = ta.ValueWhen()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    flags = [True, False, True, False, True]
    values = [Decimal(v) for v in (10, 20, 30, 40, 50)]
    got = [when.update(ctx, f, v, 1) for f, v in zip(flags, values, strict=True)]
    assert got[-1] == Decimal("30")


def test_a_pivot_is_only_confirmed_once_the_right_bars_exist():
    """Anything that claims one earlier is repainting."""
    pivot = ta.PivotHigh()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    shape = [1, 2, 5, 2, 1, 1, 1]
    got = [pivot.update(ctx, Decimal(v), 2, 2) for v in shape]
    assert is_na(got[2])
    assert got[4] == Decimal("5")


# --- guards -----------------------------------------------------------------


def test_a_length_cannot_change_mid_run():
    """One call site is one converged indicator; a new length is a new indicator."""
    sma = ta.SMA()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    sma.update(ctx, Decimal("1"), 5)
    with pytest.raises(PineRuntimeError):
        sma.update(ctx, Decimal("2"), 9)


@pytest.mark.parametrize("length", [0, -1])
def test_a_non_positive_length_is_refused(length):
    with pytest.raises(PineRuntimeError):
        ta.SMA().update(RunContext(limits=DEFAULT_LIMITS, seed=0), Decimal("1"), length)


def test_na_in_the_source_does_not_poison_the_average():
    """`na` values are skipped; the window fills from the non-na ones."""
    sma = ta.SMA()
    ctx = RunContext(limits=DEFAULT_LIMITS, seed=0)
    assert is_na(sma.update(ctx, NA, 3))
    for value in (Decimal(1), Decimal(2), Decimal(3)):
        got = sma.update(ctx, value, 3)
    assert got == Decimal("2")


def test_every_registered_factory_is_constructible():
    """A name in the subset with no factory behind it is a runtime NameError."""
    for name, factory in ta.FACTORIES.items():
        assert factory() is not None, name


# --- Q29 --------------------------------------------------------------------


def golden_files() -> list[pathlib.Path]:
    return sorted(GOLDEN.glob("*.json"))


@pytest.mark.skipif(not golden_files(), reason="Q29: no TradingView export committed yet")
@pytest.mark.parametrize("path", golden_files() or [None], ids=lambda p: getattr(p, "name", "none"))
def test_the_exported_golden_values(path):
    """Runs the moment `fixtures/pine/golden/` holds an export. See its README."""
    spec = json.loads(path.read_text())
    bars = [
        Bar(
            time=int(row["time"]),
            open=Decimal(row["open"]),
            high=Decimal(row["high"]),
            low=Decimal(row["low"]),
            close=Decimal(row["close"]),
            volume=Decimal(row["volume"]),
        )
        for row in spec["bars"]
    ]
    factory = ta.FACTORIES[spec["indicator"]]
    got = feed(factory(), bars, *spec["args"], source=spec.get("source", "close"))
    for index, expected in enumerate(spec["expected"]):
        if expected is None:
            assert is_na(got[index]), f"bar {index} should be na"
        else:
            assert near(got[index], Decimal(expected)), f"bar {index}"
