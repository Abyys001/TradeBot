"""``math.*``, ``str.*``, the null helpers, bar state, and the calendar.

Everything here is a plain function of its arguments plus the run context. The
two rules that matter:

  **Decimal in, Decimal out.** ``math.sqrt`` and ``math.log`` go through
  ``Decimal``'s own implementations rather than ``math.sqrt`` on a float,
  because these values reach ``StrategyIntent`` and from there a stop price.

  **Including trigonometry.** ``Decimal`` ships no ``sin``, and the obvious
  answer — ``math.sin`` on a float and back — would be the only ``float()`` in
  the package and would also make the same script produce different last digits
  on two hosts, since ``libm`` is not the same everywhere. So the six functions
  are argument reduction plus a Taylor series at extra precision. Slower than
  ``libm`` and portable, which is the trade this file makes everywhere else too.

  **UTC, always.** ``dayofweek`` and ``hour`` read the bar's open time in UTC
  and the panel converts for display. Pine's session functions are
  exchange-timezone aware; pretending otherwise inside the runtime is how a
  strategy that trades "the London open" trades something else on a VPS in
  another region.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext

from apps.pine.errors import PineRuntimeError
from apps.pine.series import NA, is_na, nz

ZERO = Decimal("0")
#: Fifty digits, which is more than the 24 the trig functions report and more
#: than the 40 they work at. A shorter constant makes `asin(1)` less accurate
#: than `atan(1) * 2`, which is the kind of disagreement that is invisible until
#: two expressions that should be equal are not.
_PI = Decimal("3.14159265358979323846264338327950288419716939937511")


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


#: Working precision for the series below, and the number of digits kept. The
#: gap between them is what absorbs the cancellation in the reduction step, so a
#: result is correct to every digit it shows.
_TRIG_WORK = 40
_TRIG_DIGITS = Decimal(1).scaleb(-24)


def _round_trig(value: Decimal) -> Decimal:
    return value.quantize(_TRIG_DIGITS).normalize()


def _sin_series(x: Decimal) -> Decimal:
    """Taylor about zero, on an argument already reduced into [-pi, pi]."""
    total, term, square = x, x, -x * x
    index = 1
    while True:
        index += 2
        term = term * square / (index * (index - 1))
        if term == 0 or abs(term) < Decimal(1).scaleb(-(_TRIG_WORK + 2)):
            return total + term
        total += term


def _reduce(x: Decimal) -> Decimal:
    two_pi = _PI * 2
    reduced = x - (x / two_pi).to_integral_value(rounding="ROUND_HALF_EVEN") * two_pi
    return reduced


def math_sin(ctx, x):
    if _guard(x):
        return NA
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_sin_series(_reduce(+_dec(x))))


def math_cos(ctx, x):
    if _guard(x):
        return NA
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_sin_series(_reduce(_PI / 2 - _dec(x))))


def math_tan(ctx, x):
    if _guard(x):
        return NA
    with localcontext() as context:
        context.prec = _TRIG_WORK
        angle = _reduce(+_dec(x))
        cosine = _sin_series(_reduce(_PI / 2 - angle))
        if cosine == 0:
            raise PineRuntimeError("math.tan is undefined at this angle", code="domain")
        return _round_trig(_sin_series(angle) / cosine)


def _atan_series(x: Decimal) -> Decimal:
    """``atan`` by halving the argument until the series converges quickly.

    ``atan(x) = 2 * atan(x / (1 + sqrt(1 + x^2)))`` — each application roughly
    halves ``|x|``, so five of them put any input well inside the radius where
    the alternating series needs a handful of terms.
    """
    halvings = 0
    while abs(x) > Decimal("0.05"):
        x = x / (1 + (1 + x * x).sqrt())
        halvings += 1
    total, term, square = x, x, -x * x
    index = 1
    while True:
        index += 2
        term = term * square
        contribution = term / index
        if contribution == 0 or abs(contribution) < Decimal(1).scaleb(-(_TRIG_WORK + 2)):
            break
        total += contribution
    return total * (2**halvings)


def math_atan(ctx, x):
    if _guard(x):
        return NA
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_atan_series(+_dec(x)))


def _asin(value: Decimal) -> Decimal:
    if abs(value) == 1:
        return _PI / 2 * value
    return _atan_series(value / (1 - value * value).sqrt())


def math_asin(ctx, x):
    if _guard(x):
        return NA
    value = _dec(x)
    if not (-1 <= value <= 1):
        raise PineRuntimeError("math.asin is undefined outside [-1, 1]", code="domain")
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_asin(+value))


def math_acos(ctx, x):
    if _guard(x):
        return NA
    value = _dec(x)
    if not (-1 <= value <= 1):
        raise PineRuntimeError("math.acos is undefined outside [-1, 1]", code="domain")
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_PI / 2 - _asin(+value))


def math_todegrees(ctx, radians):
    """Rounded to the same place the trig functions report at.

    Without it ``math.todegrees(math.asin(1))`` is 90.000000000000000000000018:
    the conversion runs at the default context precision and re-exposes the
    digits ``_round_trig`` had already decided not to claim.
    """
    if _guard(radians):
        return NA
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_dec(radians) * Decimal(180) / _PI)


def math_toradians(ctx, degrees):
    if _guard(degrees):
        return NA
    with localcontext() as context:
        context.prec = _TRIG_WORK
        return _round_trig(_dec(degrees) * _PI / Decimal(180))


def math_round_to_mintick(ctx, x):
    """Round to the instrument's tick. The one place ``syminfo.mintick`` is used
    for arithmetic rather than display, which is why it is fed in rather than
    guessed — see ``apps.pine.symbol``."""
    if _guard(x):
        return NA
    tick = ctx.symbol_info.mintick
    if tick <= ZERO:
        return _dec(x)
    return (_dec(x) / tick).to_integral_value(rounding="ROUND_HALF_UP") * tick


# --- str --------------------------------------------------------------------


#: ``str.tostring``'s numeric formats. Pine takes a mask of ``#`` and ``0``
#: (``"#.##"``, ``"0.000"``) or ``format.mintick``. The mask is what the example
#: dashboards in every published strategy use, and ignoring it — which this used
#: to do — prints a stop price with eighteen decimal places into a log line.
_MASK_RE = re.compile(r"^[#0,]*(?:\.([#0]+))?%?$")


def _format_number(value: Decimal, mask: str) -> str:
    match = _MASK_RE.match(mask)
    if match is None:
        return str(value)
    percent = mask.endswith("%")
    if percent:
        value = value * 100
    places = len(match.group(1) or "")
    quantized = value.quantize(
        Decimal(1).scaleb(-places) if places else Decimal(1), rounding="ROUND_HALF_UP"
    )
    text = f"{quantized:,f}" if "," in mask else f"{quantized:f}"
    if "." in text and (match.group(1) or "").endswith("#"):
        # A `#` place is dropped when it is a trailing zero; a `0` place is kept.
        keep = len((match.group(1) or "").rstrip("#"))
        head, _, tail = text.partition(".")
        tail = tail.rstrip("0")
        while len(tail) < keep:
            tail += "0"
        text = f"{head}.{tail}" if tail else head
    return f"{text}%" if percent else text


def str_tostring(ctx, value, fmt=None):
    if isinstance(value, tuple | list):
        return "[" + ", ".join(str_tostring(ctx, item) for item in value) + "]"
    if is_na(value):
        return "NaN"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal) and fmt is not None and not is_na(fmt):
        if fmt == "format.mintick":
            return _format_number(value, "#." + "#" * _mintick_places(ctx))
        return _format_number(value, str(fmt))
    return str(value)


def _mintick_places(ctx) -> int:
    tick = ctx.symbol_info.mintick
    return max(0, -tick.normalize().as_tuple().exponent)


def str_format_time(ctx, when, fmt="yyyy-MM-dd'T'HH:mm:ssZ", tz=None):
    """Pine's Java-style time mask, in UTC or the named offset.

    Only the fields real scripts use are translated. An unrecognised field is
    left alone rather than guessed at, so a mask this does not know produces a
    visibly odd string instead of a plausible wrong time.
    """
    moment = _moment(ctx, when)
    if tz and not is_na(tz):
        moment = moment.astimezone(_zone(str(tz)))
    mask, out, index = str(fmt), [], 0
    while index < len(mask):
        if mask[index] == "'":
            end = mask.find("'", index + 1)
            if end == -1:
                out.append(mask[index + 1 :])
                break
            out.append(mask[index + 1 : end])
            index = end + 1
            continue
        for token, value in _TIME_FIELDS:
            if mask.startswith(token, index):
                out.append(value(moment))
                index += len(token)
                break
        else:
            out.append(mask[index])
            index += 1
    return "".join(out)


#: Longest first, so ``yyyy`` is not read as two ``yy``.
_TIME_FIELDS: tuple[tuple[str, object], ...] = (
    ("yyyy", lambda m: f"{m.year:04d}"),
    ("yy", lambda m: f"{m.year % 100:02d}"),
    ("MMMM", lambda m: m.strftime("%B")),
    ("MMM", lambda m: m.strftime("%b")),
    ("MM", lambda m: f"{m.month:02d}"),
    ("dd", lambda m: f"{m.day:02d}"),
    ("EEEE", lambda m: m.strftime("%A")),
    ("EEE", lambda m: m.strftime("%a")),
    ("HH", lambda m: f"{m.hour:02d}"),
    ("hh", lambda m: f"{(m.hour % 12) or 12:02d}"),
    ("mm", lambda m: f"{m.minute:02d}"),
    ("ss", lambda m: f"{m.second:02d}"),
    ("SSS", lambda m: "000"),
    ("a", lambda m: "AM" if m.hour < 12 else "PM"),
    ("ZZ", lambda m: m.strftime("%z")),
    ("Z", lambda m: m.strftime("%z")),
)


def str_startswith(ctx, text, prefix):
    return str(text).startswith(str(prefix))


def str_endswith(ctx, text, suffix):
    return str(text).endswith(str(suffix))


def str_substring(ctx, text, begin, end=None):
    value = str(text)
    start = int(_dec(begin))
    stop = len(value) if end is None or is_na(end) else int(_dec(end))
    return value[start:stop]


def str_replace_all(ctx, text, target, replacement):
    return str(text).replace(str(target), str(replacement))


def str_split(ctx, text, separator):
    """A tuple, not an array — collections are outside the subset, and a tuple is
    what ``for ... in`` already walks."""
    return tuple(str(text).split(str(separator)))


def str_trim(ctx, text):
    return str(text).strip()


def str_upper(ctx, text):
    return str(text).upper()


def str_lower(ctx, text):
    return str(text).lower()


def str_repeat(ctx, text, count, separator=""):
    times = int(_dec(count))
    return str(separator).join([str(text)] * times) if times > 0 else ""


def str_pos(ctx, text, needle):
    index = str(text).find(str(needle))
    return NA if index < 0 else Decimal(index)


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


#: ``timestamp("01 Jan 2026 00:00 +1100")`` — the spelling every published
#: backtest-window input uses. Pine also accepts an ISO-ish form and a leading
#: timezone argument; all three land here.
_DATE_RE = re.compile(
    r"^\s*(?:(?P<d1>\d{1,2})\s+(?P<mon>[A-Za-z]{3,})\s+(?P<y1>\d{4})"
    r"|(?P<y2>\d{4})-(?P<m2>\d{1,2})-(?P<d2>\d{1,2}))"
    r"(?:[T ]+(?P<hh>\d{1,2}):(?P<mm>\d{2})(?::(?P<ss>\d{2}))?)?"
    r"\s*(?P<tz>[+-]\d{2}:?\d{2}|Z|UTC[+-]?\d*)?\s*$"
)

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}


def _zone(name: str):
    """A fixed offset from ``+1100``/``UTC-5``/``GMT``. Named zones are refused.

    A name like ``America/New_York`` needs a database whose contents change with
    the operating system underneath the container, which would make the same
    script produce different bars on two hosts. An offset is arithmetic.
    """
    text = name.strip().upper()
    if text in ("", "Z", "UTC", "GMT", "UTC+0", "GMT+0"):
        return UTC
    match = re.match(r"^(?:UTC|GMT)?([+-])(\d{1,2}):?(\d{2})?$", text)
    if match is None:
        raise PineRuntimeError(
            f"{name!r} is not a timezone this platform reads — use an offset like "
            f"'UTC+11' or '+1100', which means the same thing on every host",
            code="bad_timezone",
        )
    sign = 1 if match.group(1) == "+" else -1
    hours, minutes = int(match.group(2)), int(match.group(3) or 0)
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _parse_date(text: str, default_zone) -> int:
    match = _DATE_RE.match(text)
    if match is None:
        raise PineRuntimeError(
            f"timestamp() cannot read {text!r} — use '01 Jan 2026 00:00 +1100' or "
            f"'2026-01-01T00:00'",
            code="bad_timestamp",
        )
    if match.group("y1"):
        year = int(match.group("y1"))
        month = _MONTHS.get(match.group("mon")[:3].lower(), 0)
        day = int(match.group("d1"))
        if not month:
            raise PineRuntimeError(
                f"{match.group('mon')!r} is not a month name", code="bad_timestamp"
            )
    else:
        year, month, day = int(match.group("y2")), int(match.group("m2")), int(match.group("d2"))
    hour = int(match.group("hh") or 0)
    minute = int(match.group("mm") or 0)
    second = int(match.group("ss") or 0)
    zone = _zone(match.group("tz")) if match.group("tz") else default_zone
    return int(datetime(year, month, day, hour, minute, second, tzinfo=zone).timestamp())


def builtin_timestamp(ctx, *args):
    """Every form Pine has, in UNIX **seconds** — this platform's bar clock.

    ``timestamp(y, m, d[, h, mi, s])``, the same with a leading timezone string,
    and ``timestamp("01 Jan 2026 00:00 +1100")``. The string form is the one
    every "Backtest Start" input is written with, and it used to raise on the
    first bar because the argument was fed to ``int()``.
    """
    values = [a for a in args if not is_na(a)]
    if not values:
        raise PineRuntimeError("timestamp() needs a date", code="bad_timestamp")

    zone = UTC
    if isinstance(values[0], str) and len(values) > 1:
        zone = _zone(values[0])
        values = values[1:]
    if len(values) == 1 and isinstance(values[0], str):
        return _parse_date(values[0], zone)

    parts = [int(_dec(v)) for v in values]
    if len(parts) < 3:
        raise PineRuntimeError(
            "timestamp() needs at least a year, a month and a day", code="bad_timestamp"
        )
    year, month, day = parts[0], parts[1], parts[2]
    hour, minute, second = (parts + [0, 0, 0])[3:6]
    return int(datetime(year, month, day, hour, minute, second, tzinfo=zone).timestamp())


def builtin_weekofyear(ctx, when=None):
    return _moment(ctx, when).isocalendar().week


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


# --- casts ------------------------------------------------------------------


def cast_int(ctx, value=None):
    """Pine truncates towards zero — ``int(-0.9)`` is ``0``, not ``-1``."""
    if _guard(value):
        return NA
    return _dec(value).to_integral_value(rounding="ROUND_DOWN")


def cast_float(ctx, value=None):
    return NA if _guard(value) else _dec(value)


def cast_bool(ctx, value=None):
    return False if is_na(value) else bool(value)


def cast_string(ctx, value=None):
    return NA if is_na(value) else str_tostring(ctx, value)


# --- colour -----------------------------------------------------------------
#
# Inert, like every other decorative value: a colour has no arithmetic that
# produces a side, a price or a percent, so these are real functions with real
# results only so that `color.new(c, 90) == color.new(c, 90)` behaves and a
# script can hold one in a variable. Nothing downstream reads them.


def color_new(ctx, base, transparency=0):
    return f"{base}@{_dec(transparency)}"


def color_rgb(ctx, red, green, blue, transparency=0):
    return f"rgb({_dec(red)},{_dec(green)},{_dec(blue)},{_dec(transparency)})"


def color_from_gradient(ctx, value, bottom_value, top_value, bottom_color, top_color):
    if _guard(value, bottom_value, top_value):
        return bottom_color
    return top_color if _dec(value) >= _dec(top_value) else bottom_color


def _channel(ctx, _color):
    """``color.r``/``g``/``b``/``t`` — a number, because a script may compare it.

    Zero rather than a decoded channel: this platform stores a colour by its
    source spelling (``"color.green"``), which has no channels to decode, and a
    fabricated 128 would be a number a script could branch on and be wrong.
    """
    return ZERO


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
        "sin": math_sin,
        "cos": math_cos,
        "tan": math_tan,
        "asin": math_asin,
        "acos": math_acos,
        "atan": math_atan,
        "todegrees": math_todegrees,
        "toradians": math_toradians,
        "round_to_mintick": math_round_to_mintick,
    },
    "str": {
        "tostring": str_tostring,
        "tonumber": str_tonumber,
        "format": str_format,
        "format_time": str_format_time,
        "length": str_length,
        "contains": str_contains,
        "startswith": str_startswith,
        "endswith": str_endswith,
        "substring": str_substring,
        "replace_all": str_replace_all,
        "split": str_split,
        "trim": str_trim,
        "upper": str_upper,
        "lower": str_lower,
        "repeat": str_repeat,
        "pos": str_pos,
    },
    "color": {
        "new": color_new,
        "rgb": color_rgb,
        "from_gradient": color_from_gradient,
        "r": _channel,
        "g": _channel,
        "b": _channel,
        "t": _channel,
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
    "weekofyear": builtin_weekofyear,
    "int": cast_int,
    "float": cast_float,
    "bool": cast_bool,
    "string": cast_string,
    "color": lambda ctx, value=None: value,
}

NAMESPACE_CONSTANTS: dict[str, dict[str, object]] = {
    "math": {
        "pi": _PI,
        "e": Decimal("2.71828182845904523536"),
        "phi": Decimal("1.61803398874989484820"),
        "rphi": Decimal("0.61803398874989484820"),
    },
}

#: Bare names that are *values* of the current bar rather than calls.
CALENDAR_VALUES = {
    "weekofyear": builtin_weekofyear,
    "dayofweek": builtin_dayofweek,
    "hour": builtin_hour,
    "minute": builtin_minute,
    "second": builtin_second,
    "year": builtin_year,
    "month": builtin_month,
    "dayofmonth": builtin_dayofmonth,
}
