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


# --- timestamp, in the spellings scripts actually use ------------------------


def test_the_date_string_form_is_read(ctx):
    """`input.time(timestamp("01 Jan 2026 00:00 +1100"))` — every backtest window.

    This used to reach `int()` on a string and raise on the first bar of any
    script that declared one.
    """
    assert bi.builtin_timestamp(ctx, "01 Jan 2026 00:00 +1100") == 1767186000


def test_the_iso_form_and_the_numeric_form_agree(ctx):
    assert bi.builtin_timestamp(ctx, "2026-01-01T00:00") == bi.builtin_timestamp(
        ctx, 2026, 1, 1, 0, 0
    )


def test_a_leading_timezone_argument_shifts_the_result(ctx):
    utc = bi.builtin_timestamp(ctx, "UTC", 2026, 1, 1)
    plus_two = bi.builtin_timestamp(ctx, "UTC+2", 2026, 1, 1)
    assert utc - plus_two == 7200


def test_a_named_timezone_is_refused_rather_than_guessed(ctx):
    """A zone database changes with the host; an offset is arithmetic."""
    with pytest.raises(PineRuntimeError) as caught:
        bi.builtin_timestamp(ctx, "America/New_York", 2026, 1, 1)
    assert caught.value.code == "bad_timezone"


def test_an_unreadable_date_says_so_instead_of_returning_a_plausible_one(ctx):
    with pytest.raises(PineRuntimeError) as caught:
        bi.builtin_timestamp(ctx, "sometime next Tuesday")
    assert caught.value.code == "bad_timestamp"


# --- str.tostring formats ----------------------------------------------------


@pytest.mark.parametrize(
    ("value", "mask", "expected"),
    [
        ("12.3456", "#.##", "12.35"),
        ("12.3000", "#.##", "12.3"),
        ("12.3000", "0.00", "12.30"),
        ("12", "#.##", "12"),
        ("-0.005", "#.##", "-0.01"),
        ("1234.5", "#", "1235"),
    ],
)
def test_a_number_format_is_honoured_rather_than_ignored(ctx, value, mask, expected):
    """`str.tostring(pnl, "#.##")` is in every published dashboard.

    Ignoring the mask — which this used to do — prints a stop price with
    eighteen decimal places into a log line.
    """
    assert bi.str_tostring(ctx, D(value), mask) == expected


def test_format_mintick_follows_the_instruments_own_tick(ctx):
    from apps.pine.symbol import SymbolInfo

    ctx.symbol_info = SymbolInfo.for_symbol("BTCUSDT", mintick=D("0.1"))
    assert bi.str_tostring(ctx, D("61234.5678"), "format.mintick") == "61234.6"


def test_a_value_with_no_format_is_unchanged(ctx):
    assert bi.str_tostring(ctx, D("12.30")) == "12.30"
    assert bi.str_tostring(ctx, NA) == "NaN"
    assert bi.str_tostring(ctx, True) == "true"


# --- str.format_time ---------------------------------------------------------


def test_a_time_mask_is_translated_field_by_field(ctx):
    assert bi.str_format_time(ctx, ctx.bar.time, "yyyy-MM-dd HH:mm") == "2024-01-03 14:30"


def test_quoted_text_inside_a_mask_is_passed_through(ctx):
    assert bi.str_format_time(ctx, ctx.bar.time, "yyyy'T'HH") == "2024T14"


def test_a_mask_field_this_does_not_know_is_left_alone(ctx):
    """Visibly odd beats a plausible wrong time."""
    assert "Q" in bi.str_format_time(ctx, ctx.bar.time, "yyyy Q")


# --- trigonometry ------------------------------------------------------------


def test_trigonometry_stays_in_decimal(ctx):
    """No `float()` anywhere in the package — `test_pine_purity` enforces it.

    The point is not precision for its own sake: `libm` is not identical on
    every host, and a runtime whose last digit depends on the machine is one
    that cannot promise a replay reproduces.
    """
    assert isinstance(bi.math_sin(ctx, D("1")), D)
    assert bi.math_sin(ctx, D("0")) == 0
    assert bi.math_cos(ctx, D("0")) == 1
    # Two routes to pi that must not disagree inside the digits either claims.
    assert bi.math_atan(ctx, D("1")) * 4 == bi.math_asin(ctx, D("1")) * 2
    # A round trip through a rounded value cannot be exact at *any* fixed
    # precision — the first conversion has already dropped digits — so the
    # promise is the reported precision, not an identity.
    assert abs(bi.math_todegrees(ctx, bi.math_asin(ctx, D("1"))) - 90) < D("1e-20")


@pytest.mark.parametrize("func", [bi.math_asin, bi.math_acos])
def test_an_arc_function_outside_its_domain_raises_rather_than_returning_na(ctx, func):
    with pytest.raises(PineRuntimeError):
        func(ctx, D("2"))


def test_round_to_mintick_uses_the_instrument(ctx):
    from apps.pine.symbol import SymbolInfo

    ctx.symbol_info = SymbolInfo.for_symbol("BTCUSDT", mintick=D("0.5"))
    assert bi.math_round_to_mintick(ctx, D("100.3")) == D("100.5")


# --- casts -------------------------------------------------------------------


def test_int_truncates_towards_zero_the_way_pine_does(ctx):
    assert bi.cast_int(ctx, D("-0.9")) == 0
    assert bi.cast_int(ctx, D("1.9")) == 1


def test_a_cast_of_na_is_na_not_zero(ctx):
    assert is_na(bi.cast_int(ctx, NA))
    assert is_na(bi.cast_float(ctx, NA))
