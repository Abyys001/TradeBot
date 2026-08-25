"""`docs/bot-plan.md` §4 — `math.*`, `str.*`, `na` handling, the calendar."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.pine import builtins as bi
from apps.pine.bar import Bar
from apps.pine.errors import PineRuntimeError
from apps.pine.limits import DEFAULT_LIMITS
from apps.pine.runtime import RunContext
from apps.pine.series import NA, is_na

D = Decimal


@pytest.fixture
def ctx():
    context = RunContext(limits=DEFAULT_LIMITS, seed=1)
    # 2024-01-03 14:30:00 UTC — a Wednesday, so `dayofweek` has something to say.
    context.bar = Bar(
        time=1704292200, open=D("100"), high=D("110"), low=D("90"), close=D("105"),
        volume=D("7"),
    )
    for name in ("open", "high", "low", "close", "volume"):
        context.series[name].push(getattr(context.bar, name))
    context.series["time"].push(D(context.bar.time))
    return context


# --- math -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fn", "args", "expected"),
    [
        (bi.math_abs, (D("-3.5"),), D("3.5")),
        (bi.math_max, (D("1"), D("9"), D("4")), D("9")),
        (bi.math_min, (D("1"), D("9"), D("4")), D("1")),
        (bi.math_pow, (D("2"), D("10")), D("1024")),
        (bi.math_sqrt, (D("16"),), D("4")),
        (bi.math_floor, (D("2.9"),), D("2")),
        (bi.math_ceil, (D("2.1"),), D("3")),
        (bi.math_sign, (D("-2"),), D("-1")),
        (bi.math_sign, (D("0"),), D("0")),
        (bi.math_avg, (D("2"), D("4")), D("3")),
        (bi.math_sum, (D("2"), D("4")), D("6")),
    ],
)
def test_math_functions(ctx, fn, args, expected):
    assert fn(ctx, *args) == expected


def test_round_takes_a_precision(ctx):
    assert bi.math_round(ctx, D("2.34567"), 2) == D("2.35")


def test_round_with_no_precision_is_to_the_whole_number(ctx):
    assert bi.math_round(ctx, D("2.6")) == D("3")


def test_floor_of_a_negative_rounds_down_not_toward_zero(ctx):
    assert bi.math_floor(ctx, D("-2.1")) == D("-3")


def test_log_and_exp_round_trip(ctx):
    assert abs(bi.math_exp(ctx, bi.math_log(ctx, D("5"))) - D("5")) < D("0.0000001")


def test_log_of_zero_is_refused_rather_than_returning_infinity(ctx):
    with pytest.raises(PineRuntimeError):
        bi.math_log(ctx, D("0"))


def test_sqrt_of_a_negative_stops_rather_than_propagating_na(ctx):
    """TradingView answers NaN. A halt is the louder divergence, and the right one:
    a negative under a square root is a formula that has gone wrong, and `na`
    would travel silently into the next comparison and read as false."""
    with pytest.raises(PineRuntimeError):
        bi.math_sqrt(ctx, D("-1"))


@pytest.mark.parametrize(
    "fn", [bi.math_abs, bi.math_sqrt, bi.math_floor, bi.math_ceil, bi.math_sign]
)
def test_na_in_means_na_out(ctx, fn):
    assert is_na(fn(ctx, NA))


def test_random_is_reproducible_from_the_seed(ctx):
    """A strategy using it must still backtest the same twice (§5 determinism)."""
    first = [bi.math_random(ctx, 0, 100) for _ in range(5)]
    other = RunContext(limits=DEFAULT_LIMITS, seed=1)
    second = [bi.math_random(other, 0, 100) for _ in range(5)]
    assert first == second


def test_math_constants_are_decimals(ctx):
    assert isinstance(bi.NAMESPACE_CONSTANTS["math"]["pi"], Decimal)


# --- str --------------------------------------------------------------------


def test_tostring_renders_a_decimal_without_scientific_notation(ctx):
    assert bi.str_tostring(ctx, D("0.00001")) == "0.00001"


def test_tostring_of_na_says_na(ctx):
    assert bi.str_tostring(ctx, NA) == "NaN"


def test_tonumber_parses(ctx):
    assert bi.str_tonumber(ctx, "3.5") == D("3.5")


def test_tonumber_of_nonsense_is_na_not_an_error(ctx):
    assert is_na(bi.str_tonumber(ctx, "abc"))


def test_format_substitutes_positionally(ctx):
    assert bi.str_format(ctx, "{0} and {1}", "a", "b") == "a and b"


def test_length_and_contains(ctx):
    assert bi.str_length(ctx, "abcd") == 4
    assert bi.str_contains(ctx, "abcd", "bc") is True
    assert bi.str_contains(ctx, "abcd", "zz") is False


# --- na handling ------------------------------------------------------------


def test_na_of_a_value_is_the_test(ctx):
    assert bi.builtin_na(ctx, NA) is True
    assert bi.builtin_na(ctx, D("1")) is False


def test_nz_defaults_to_zero(ctx):
    assert bi.builtin_nz(ctx, NA) == D("0")


def test_fixnan_holds_the_last_real_value(ctx):
    assert is_na(bi.builtin_fixnan(ctx, NA))
    assert bi.builtin_fixnan(ctx, D("5")) == D("5")
    assert bi.builtin_fixnan(ctx, NA) == D("5")


# --- calendar ---------------------------------------------------------------


def test_the_calendar_reads_the_bar_time_by_default(ctx):
    assert bi.builtin_year(ctx) == 2024
    assert bi.builtin_month(ctx) == 1
    assert bi.builtin_dayofmonth(ctx) == 3
    assert bi.builtin_hour(ctx) == 14
    assert bi.builtin_minute(ctx) == 30


def test_dayofweek_follows_pines_sunday_is_one(ctx):
    """2024-01-03 is a Wednesday, which Pine numbers 4."""
    assert bi.builtin_dayofweek(ctx) == 4


def test_the_calendar_takes_an_explicit_time(ctx):
    assert bi.builtin_year(ctx, D("1704292200")) == 2024


def test_timestamp_builds_one_from_parts(ctx):
    assert bi.builtin_timestamp(ctx, 2024, 1, 3, 14, 30, 0) == 1704292200


def test_the_calendar_is_utc_not_the_servers_timezone(ctx):
    """A bot's session filter must mean the same thing on any host."""
    assert bi.builtin_hour(ctx, D("0")) == 0


# --- the registries ---------------------------------------------------------


def test_every_subset_math_name_has_an_implementation():
    from apps.pine.subset import NAMESPACE_FUNCTIONS

    assert NAMESPACE_FUNCTIONS["math"] <= set(bi.NAMESPACE_CALLS["math"])


def test_every_subset_str_name_has_an_implementation():
    from apps.pine.subset import NAMESPACE_FUNCTIONS

    assert NAMESPACE_FUNCTIONS["str"] <= set(bi.NAMESPACE_CALLS["str"])


def test_every_bare_call_in_the_subset_has_an_implementation():
    from apps.pine.subset import BARE_FUNCTIONS, VISUAL_FUNCTIONS

    #  `input`, `strategy` and the visual calls are handled by the runtime itself.
    handled_elsewhere = {"input", "strategy"} | VISUAL_FUNCTIONS
    assert (BARE_FUNCTIONS - handled_elsewhere) <= set(bi.BARE_CALLS)
