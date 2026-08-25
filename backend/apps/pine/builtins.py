"""``math.*``, ``str.*``, the null helpers, bar state, and the calendar.

Everything here is a plain function of its arguments plus the run context. The
two rules that matter:

  **Decimal in, Decimal out.** ``math.sqrt`` and ``math.log`` go through
  ``Decimal``'s own implementations rather than ``math.sqrt`` on a float,
  because these values reach ``StrategyIntent`` and from there a stop price.

  **UTC, always.** ``dayofweek`` and ``hour`` read the bar's open time in UTC
  and the panel converts for display. Pine's session functions are
  exchange-timezone aware; pretending otherwise inside the runtime is how a
  strategy that trades "the London open" trades something else on a VPS in
  another region.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from apps.pine.errors import PineRuntimeError
from apps.pine.series import NA, is_na, nz

ZERO = Decimal("0")


def _dec(value):
    if isinstance(value, Decimal):
        return value
    if value is NA or value is None:
        return NA
    if isinstance(value, bool):
        return Decimal(1) if value else ZERO
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise PineRuntimeError(f"{value!r} is not a number", code="not_a_number") from exc


def _guard(*values):
    """``na`` in, ``na`` out — the propagation rule, in one place."""
    return any(is_na(_dec(v)) for v in values)


# --- math -------------------------------------------------------------------


def math_abs(ctx, x):
    return NA if _guard(x) else abs(_dec(x))


def math_max(ctx, *values):
    items = [_dec(v) for v in values]
    return NA if any(is_na(i) for i in items) else max(items)


def math_min(ctx, *values):
    items = [_dec(v) for v in values]
    return NA if any(is_na(i) for i in items) else min(items)


def math_pow(ctx, base, exponent):
    if _guard(base, exponent):
        return NA
    x, y = _dec(base), _dec(exponent)
    if y == y.to_integral_value():
        return x ** int(y)
    if x <= ZERO:
        raise PineRuntimeError(
            "math.pow with a fractional exponent needs a positive base", code="domain"
        )
    # Decimal has no general power, so go through the identity. Kept explicit
    # rather than dropping to float, which is the only other option.
    return (y * x.ln()).exp()


def math_sqrt(ctx, x):
    if _guard(x):
        return NA
    value = _dec(x)
    if value < ZERO:
        raise PineRuntimeError("math.sqrt of a negative number", code="domain")
    return value.sqrt()


def math_log(ctx, x):
    if _guard(x):
        return NA
    value = _dec(x)
    if value <= ZERO:
        raise PineRuntimeError("math.log needs a positive number", code="domain")
    return value.ln()


def math_log10(ctx, x):
    if _guard(x):
        return NA
    value = _dec(x)
    if value <= ZERO:
        raise PineRuntimeError("math.log10 needs a positive number", code="domain")
    return value.log10()


def math_exp(ctx, x):
    return NA if _guard(x) else _dec(x).exp()


def math_round(ctx, x, precision=None):
    if _guard(x):
        return NA
    value = _dec(x)
    if precision is None:
        return value.to_integral_value(rounding="ROUND_HALF_UP")
    places = int(precision)
    return value.quantize(Decimal(1).scaleb(-places), rounding="ROUND_HALF_UP")


def math_floor(ctx, x):
    return NA if _guard(x) else _dec(x).to_integral_value(rounding="ROUND_FLOOR")


def math_ceil(ctx, x):
    return NA if _guard(x) else _dec(x).to_integral_value(rounding="ROUND_CEILING")


def math_sign(ctx, x):
    if _guard(x):
        return NA
    value = _dec(x)
    return Decimal(0) if value == ZERO else (Decimal(1) if value > ZERO else Decimal(-1))


def math_avg(ctx, *values):
    items = [_dec(v) for v in values]
    if any(is_na(i) for i in items) or not items:
        return NA
    return sum(items, ZERO) / Decimal(len(items))


def math_sum(ctx, *values):
    items = [_dec(v) for v in values]
    return NA if any(is_na(i) for i in items) else sum(items, ZERO)


def math_random(ctx, minimum=0, maximum=1, seed=None):
    """From the run's own seeded generator, never the module-level one.

    Determinism is a test in this project, not an aspiration: the same bars must
    produce the same intents twice. A script calling ``math.random`` is still
    deterministic because the seed is fixed for the run and recorded with it.
    """
    low, high = _dec(minimum), _dec(maximum)
    if is_na(low) or is_na(high):
        return NA
    return low + (high - low) * Decimal(str(ctx.random.random()))


# --- str --------------------------------------------------------------------


def str_tostring(ctx, value, _format=None):
    if is_na(value):
        return "NaN"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def str_tonumber(ctx, value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return NA


def str_format(ctx, template, *values):
    """Pine's ``{0}``-style placeholders. Unlike ``str.format`` in Python this
    never raises on a missing key — a log line is not worth stopping a bot for."""
    text = str(template)
    for index, value in enumerate(values):
        text = text.replace("{" + str(index) + "}", str_tostring(ctx, value))
    return text


def str_length(ctx, value):
    return Decimal(len(str(value)))


def str_contains(ctx, haystack, needle):
    return str(needle) in str(haystack)


# --- nulls ------------------------------------------------------------------


def builtin_na(ctx, value=None):
    """``na`` bare is the value; ``na(x)`` is the test. One name, two meanings —
    the runtime resolves which by whether it was called."""
    return is_na(value)


def builtin_nz(ctx, value, replacement=None):
    return nz(value, replacement)


def builtin_fixnan(ctx, value):
    """``na`` becomes the last non-``na`` value this call site saw."""
    state = ctx.scratch.setdefault("fixnan", {})
    key = ctx.current_call_id
    if not is_na(value):
        state[key] = value
        return value
    return state.get(key, NA)


# --- calendar ---------------------------------------------------------------


def _moment(ctx, when=None) -> datetime:
    seconds = ctx.bar.time if when is None or is_na(when) else int(_dec(when))
    # Pine's `time` is in milliseconds; this platform's bar times are seconds.
    # A value that large can only be the millisecond form, so accept both rather
    # than making every script remember which side of the boundary it is on.
    if seconds > 10_000_000_000:
        seconds //= 1000
    return datetime.fromtimestamp(seconds, tz=UTC)


def builtin_timestamp(ctx, *args):
    """``timestamp(year, month, day, hour, minute, second)``, UTC, in seconds."""
    parts = [int(_dec(a)) for a in args if not is_na(a)]
    if len(parts) < 3:
        raise PineRuntimeError(
            "timestamp() needs at least a year, a month and a day", code="bad_timestamp"
        )
    year, month, day = parts[0], parts[1], parts[2]
    hour, minute, second = (parts + [0, 0, 0])[3:6]
    return int(datetime(year, month, day, hour, minute, second, tzinfo=UTC).timestamp())


def builtin_dayofweek(ctx, when=None):
    # Pine numbers Sunday as 1; Python's isoweekday makes Sunday 7.
    return (_moment(ctx, when).isoweekday() % 7) + 1


def builtin_hour(ctx, when=None):
    return _moment(ctx, when).hour


def builtin_minute(ctx, when=None):
    return _moment(ctx, when).minute


def builtin_second(ctx, when=None):
    return _moment(ctx, when).second


def builtin_year(ctx, when=None):
    return _moment(ctx, when).year


def builtin_month(ctx, when=None):
    return _moment(ctx, when).month


def builtin_dayofmonth(ctx, when=None):
    return _moment(ctx, when).day


# --- registry ---------------------------------------------------------------

NAMESPACE_CALLS: dict[str, dict[str, object]] = {
    "math": {
        "abs": math_abs,
        "max": math_max,
        "min": math_min,
        "pow": math_pow,
        "sqrt": math_sqrt,
        "log": math_log,
        "log10": math_log10,
        "exp": math_exp,
        "round": math_round,
        "floor": math_floor,
        "ceil": math_ceil,
        "sign": math_sign,
        "avg": math_avg,
        "sum": math_sum,
        "random": math_random,
    },
    "str": {
        "tostring": str_tostring,
        "tonumber": str_tonumber,
        "format": str_format,
        "length": str_length,
        "contains": str_contains,
    },
}

BARE_CALLS: dict[str, object] = {
    "na": builtin_na,
    "nz": builtin_nz,
    "fixnan": builtin_fixnan,
    "timestamp": builtin_timestamp,
    "dayofweek": builtin_dayofweek,
    "hour": builtin_hour,
    "minute": builtin_minute,
    "second": builtin_second,
    "year": builtin_year,
    "month": builtin_month,
    "dayofmonth": builtin_dayofmonth,
    "max": math_max,
    "min": math_min,
    "abs": math_abs,
}

NAMESPACE_CONSTANTS: dict[str, dict[str, object]] = {
    "math": {"pi": Decimal("3.14159265358979323846"), "e": Decimal("2.71828182845904523536")},
}

#: Bare names that are *values* of the current bar rather than calls.
CALENDAR_VALUES = {
    "dayofweek": builtin_dayofweek,
    "hour": builtin_hour,
    "minute": builtin_minute,
    "second": builtin_second,
    "year": builtin_year,
    "month": builtin_month,
    "dayofmonth": builtin_dayofmonth,
}
