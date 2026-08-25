"""`docs/bot-plan.md` §4 — `na` as a value, and the bounded series."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.pine.series import NA, Series, is_na, nz

# --- na ---------------------------------------------------------------------


def test_na_is_falsy():
    assert not NA


def test_na_is_a_singleton():
    assert NA is NA
    assert is_na(NA)


def test_none_is_not_na():
    """`NA` is the only `na`. A Python `None` arriving here is a bug, not a value."""
    assert not is_na(None)


@pytest.mark.parametrize("op", ["add", "sub", "mul", "truediv"])
def test_arithmetic_on_na_yields_na(op):
    import operator

    fn = getattr(operator, op)
    assert is_na(fn(NA, Decimal("2")))
    assert is_na(fn(Decimal("2"), NA))


@pytest.mark.parametrize("op", ["lt", "le", "gt", "ge"])
def test_every_comparison_with_na_is_false(op):
    """Not `na`, and not an exception — this is what makes `close > sma` safe."""
    import operator

    fn = getattr(operator, op)
    assert fn(NA, Decimal("2")) is False
    assert fn(Decimal("2"), NA) is False


def test_na_equals_nothing_including_itself():
    assert (NA == NA) is False
    assert (NA == Decimal("0")) is False


def test_negating_na_is_na():
    assert is_na(-NA)


def test_nz_replaces_na_with_zero_by_default():
    assert nz(NA) == Decimal("0")


def test_nz_takes_an_explicit_replacement():
    assert nz(NA, Decimal("5")) == Decimal("5")


def test_nz_leaves_a_real_value_alone():
    assert nz(Decimal("3")) == Decimal("3")


# --- Series -----------------------------------------------------------------


def test_offset_zero_is_the_current_bar():
    s = Series(10)
    s.push(Decimal("1"))
    s.push(Decimal("2"))
    assert s[0] == Decimal("2")


def test_offset_one_is_the_previous_bar():
    s = Series(10)
    s.push(Decimal("1"))
    s.push(Decimal("2"))
    assert s[1] == Decimal("1")


def test_reading_past_the_start_of_history_is_na_not_an_error():
    s = Series(10)
    s.push(Decimal("1"))
    assert is_na(s[5])


def test_an_empty_series_reads_na():
    assert is_na(Series(10)[0])


def test_a_negative_offset_cannot_read_forward():
    s = Series(10)
    s.push(Decimal("1"))
    with pytest.raises(IndexError):
        s[-1]


def test_the_series_is_capped():
    """A month of 1m bars must not become a month of memory.

    Trimmed in blocks, so the bound is twice the depth rather than the depth —
    one slice every `depth` bars instead of a list shuffle on every one.
    """
    s = Series(5)
    for value in range(100):
        s.push(Decimal(value))
    assert len(s) <= 10
    assert s[0] == Decimal("99")
    assert s[4] == Decimal("95")


def test_a_trimmed_series_reads_na_beyond_the_cap():
    s = Series(3)
    for value in range(100):
        s.push(Decimal(value))
    assert is_na(s[50])


def test_set_overwrites_the_current_bar_rather_than_appending():
    """`x := 2` inside a bar rewrites this bar's value; it does not add one."""
    s = Series(10)
    s.push(Decimal("1"))
    s.set(Decimal("2"))
    assert s[0] == Decimal("2")
    assert len(s) == 1


def test_value_is_the_current_bar():
    s = Series(10)
    s.push(Decimal("7"))
    assert s.value == Decimal("7")
