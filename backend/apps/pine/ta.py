"""The ``ta.*`` library: every indicator as an incremental ``update()``.

Three properties every class here holds to, and each one is load-bearing:

  **Incremental, O(1) or O(window) per bar.** Never recompute a window from
  scratch on every bar. That is the difference between a 100k-bar backtest that
  finishes in seconds and one that takes an afternoon, and a backtest nobody
  runs is a backtest that proves nothing.

  **TradingView's warm-up, exactly.** ``ta.sma(close, 20)`` is ``na`` for the
  first nineteen bars, and the ``rma`` family — ``rsi``, ``atr``, and everything
  built on them — seeds the first period with a *simple average* before going
  recursive. Built from the textbook recurrence instead, an RSI is off by a few
  tenths **forever**; a few tenths is enough to flip a ``crossover``, and a
  flipped crossover is a trade that should not have happened at 99% of every
  partner's balance. Q29 covers where the reference numbers come from.

  **``Decimal``.** These values become stop prices. The project-wide rule holds
  here with no exception carved out for speed — the arithmetic is a few hundred
  thousand operations per backtest, which Decimal does comfortably.

Each object is created lazily by the runtime, keyed on
``(call_id, call_stack_path)``, so ``ta.ema(close, 20)`` on line 12 and the same
text on line 30 are two different EMAs — which they are.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from apps.pine.errors import PineRuntimeError
from apps.pine.series import NA, is_na

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is NA or value is None:
        return NA
    if isinstance(value, bool):
        return ONE if value else ZERO
    return Decimal(str(value))


def _int(value, what: str) -> int:
    if is_na(value):
        raise PineRuntimeError(f"{what} is na", code="na_length")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PineRuntimeError(f"{what} must be a whole number", code="bad_length") from exc


class Indicator:
    """Base. ``update(ctx, *args)`` returns this bar's value.

    ``ctx`` is the run context, passed to every indicator rather than only the
    ones that need it: ``ta.atr`` and ``ta.tr`` read the bar's high/low/close
    themselves rather than taking them as arguments, exactly as Pine does, and a
    uniform signature means the runtime has no per-indicator special case.
    """

    __slots__ = ("length",)

    def __init__(self) -> None:
        self.length = 0

    def _fix_length(self, value, what: str = "length") -> int:
        """Pin the window on the first bar and refuse a change after it.

        TradingView types these arguments as *simple* — constant for the run —
        and for good reason: an EMA whose period changes mid-series is not an
        EMA of anything. Refusing loudly beats silently restarting the average.
        """
        length = _int(value, what)
        if length <= 0:
            raise PineRuntimeError(f"{what} must be positive, got {length}", code="bad_length")
        if self.length and length != self.length:
            raise PineRuntimeError(
                f"{what} changed from {self.length} to {length} mid-run — this platform "
                f"types it as constant, the way TradingView does",
                code="length_changed",
            )
        self.length = length
        return length

    def update(self, ctx, *args):  # pragma: no cover - abstract
        raise NotImplementedError


# --- rolling primitives -----------------------------------------------------


class _Window:
    """A bounded window with a running total. The workhorse under most of these."""

    __slots__ = ("n", "buf", "total")

    def __init__(self, n: int) -> None:
        self.n = n
        self.buf: deque[Decimal] = deque(maxlen=n)
        self.total = ZERO

    def push(self, value: Decimal) -> None:
        if len(self.buf) == self.n:
            self.total -= self.buf[0]
        self.buf.append(value)
        self.total += value

    @property
    def full(self) -> bool:
        return len(self.buf) == self.n

    def mean(self) -> Decimal:
        return self.total / self.n


# --- moving averages --------------------------------------------------------


class SMA(Indicator):
    __slots__ = ("win",)

    def __init__(self) -> None:
        super().__init__()
        self.win: _Window | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.win is None:
            self.win = _Window(n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.win.push(value)
        return self.win.mean() if self.win.full else NA


class EMA(Indicator):
    """Seeded with the SMA of the first ``length`` bars, then recursive.

    TradingView seeds this way; the textbook "start from the first value"
    variant converges to a different series and never catches up.
    """

    __slots__ = ("win", "prev", "alpha")

    def __init__(self) -> None:
        super().__init__()
        self.win: _Window | None = None
        self.prev = NA
        self.alpha = ZERO

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.win is None:
            self.win = _Window(n)
            self.alpha = Decimal(2) / Decimal(n + 1)
        value = _dec(source)
        if is_na(value):
            return NA
        if is_na(self.prev):
            self.win.push(value)
            if not self.win.full:
                return NA
            self.prev = self.win.mean()
            return self.prev
        self.prev = self.alpha * value + (ONE - self.alpha) * self.prev
        return self.prev


class RMA(Indicator):
    """Wilder's smoothing, with TradingView's seed. The whole ``rsi``/``atr``
    family sits on this, so an error here is an error in all of them."""

    __slots__ = ("win", "prev")

    def __init__(self) -> None:
        super().__init__()
        self.win: _Window | None = None
        self.prev = NA

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.win is None:
            self.win = _Window(n)
        value = _dec(source)
        if is_na(value):
            return NA
        if is_na(self.prev):
            self.win.push(value)
            if not self.win.full:
                return NA
            self.prev = self.win.mean()
            return self.prev
        self.prev = (self.prev * Decimal(n - 1) + value) / Decimal(n)
        return self.prev


class WMA(Indicator):
    __slots__ = ("buf",)

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque[Decimal] | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.buf.append(value)
        if len(self.buf) < n:
            return NA
        return self._weighted(self.buf, n)

    @staticmethod
    def _weighted(values, n: int) -> Decimal:
        total = ZERO
        weight_sum = Decimal(n * (n + 1) // 2)
        # Oldest carries weight 1, newest carries weight n.
        for index, item in enumerate(values, start=1):
            total += item * Decimal(index)
        return total / weight_sum


class VWMA(Indicator):
    __slots__ = ("price_win", "volume_win")

    def __init__(self) -> None:
        super().__init__()
        self.price_win: _Window | None = None
        self.volume_win: _Window | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.price_win is None:
            self.price_win = _Window(n)
            self.volume_win = _Window(n)
        value = _dec(source)
        volume = _dec(ctx.builtin("volume"))
        if is_na(value) or is_na(volume):
            return NA
        self.price_win.push(value * volume)
        self.volume_win.push(volume)
        if not self.price_win.full or self.volume_win.total == ZERO:
            return NA
        return self.price_win.total / self.volume_win.total


class HMA(Indicator):
    """``wma(2*wma(src, n/2) - wma(src, n), sqrt(n))`` — three windows, one value."""

    __slots__ = ("half", "full_wma", "root", "root_n")

    def __init__(self) -> None:
        super().__init__()
        self.half: deque[Decimal] | None = None
        self.full_wma: deque[Decimal] | None = None
        self.root: deque[Decimal] | None = None
        self.root_n = 0

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.half is None:
            half_n = max(1, n // 2)
            self.root_n = max(1, int(Decimal(n).sqrt()))
            self.half = deque(maxlen=half_n)
            self.full_wma = deque(maxlen=n)
            self.root = deque(maxlen=self.root_n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.half.append(value)
        self.full_wma.append(value)
        if len(self.half) < self.half.maxlen or len(self.full_wma) < n:
            return NA
        raw = Decimal(2) * WMA._weighted(self.half, self.half.maxlen) - WMA._weighted(
            self.full_wma, n
        )
        self.root.append(raw)
        if len(self.root) < self.root_n:
            return NA
        return WMA._weighted(self.root, self.root_n)


# --- dispersion -------------------------------------------------------------


class Variance(Indicator):
    """Population variance, which is what TradingView's ``biased=true`` default is."""

    __slots__ = ("win",)

    def __init__(self) -> None:
        super().__init__()
        self.win: _Window | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.win is None:
            self.win = _Window(n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.win.push(value)
        if not self.win.full:
            return NA
        mean = self.win.mean()
        return sum(((item - mean) ** 2 for item in self.win.buf), ZERO) / Decimal(n)


class Stdev(Variance):
    def update(self, ctx, source, length):
        variance = super().update(ctx, source, length)
        return NA if is_na(variance) else variance.sqrt()


# --- momentum ---------------------------------------------------------------


class Change(Indicator):
    """``src - src[n]``. ``mom`` is the same thing under another name."""

    __slots__ = ("buf",)

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque | None = None

    def update(self, ctx, source, length=1):
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n + 1)
        value = _dec(source)
        self.buf.append(value)
        if len(self.buf) < n + 1:
            return NA
        old = self.buf[0]
        if is_na(value) or is_na(old):
            return NA
        return value - old


class ROC(Change):
    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n + 1)
        value = _dec(source)
        self.buf.append(value)
        if len(self.buf) < n + 1:
            return NA
        old = self.buf[0]
        if is_na(value) or is_na(old) or old == ZERO:
            return NA
        return (value - old) / old * HUNDRED


class RSI(Indicator):
    __slots__ = ("up", "down", "prev")

    def __init__(self) -> None:
        super().__init__()
        self.up = RMA()
        self.down = RMA()
        self.prev = NA

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        value = _dec(source)
        if is_na(value):
            return NA
        if is_na(self.prev):
            self.prev = value
            # The first bar has no change to measure, so it feeds the averages
            # *nothing*. Pine's `math.max(close - close[1], 0)` is `na` here and
            # `ta.rma` skips `na`; pushing a zero instead would both drag the
            # seed average down and hand back the first reading a bar early.
            return NA
        delta = value - self.prev
        self.prev = value
        gain = self.up.update(ctx, delta if delta > ZERO else ZERO, n)
        loss = self.down.update(ctx, -delta if delta < ZERO else ZERO, n)
        if is_na(gain) or is_na(loss):
            return NA
        if loss == ZERO:
            return HUNDRED
        if gain == ZERO:
            return ZERO
        return HUNDRED - HUNDRED / (ONE + gain / loss)


class TrueRange(Indicator):
    """``max(high-low, |high-close[1]|, |low-close[1]|)``.

    ``handle_na=false`` is TradingView's default and makes the first bar ``na``;
    ``ta.tr(true)`` makes it ``high-low`` instead. ``ta.atr`` uses the second,
    which is why an ATR has a value on the bar an ``ta.tr`` still does not.
    """

    __slots__ = ("prev_close",)

    def __init__(self) -> None:
        super().__init__()
        self.prev_close = NA

    def update(self, ctx, handle_na=False):
        high = _dec(ctx.builtin("high"))
        low = _dec(ctx.builtin("low"))
        close = _dec(ctx.builtin("close"))
        previous = self.prev_close
        self.prev_close = close
        if is_na(previous):
            return (high - low) if handle_na else NA
        return max(high - low, abs(high - previous), abs(low - previous))


class ATR(Indicator):
    __slots__ = ("tr", "rma")

    def __init__(self) -> None:
        super().__init__()
        self.tr = TrueRange()
        self.rma = RMA()

    def update(self, ctx, length):
        n = self._fix_length(length)
        return self.rma.update(ctx, self.tr.update(ctx, True), n)


class MACD(Indicator):
    """Returns ``[macd, signal, histogram]`` — a tuple the caller destructures."""

    __slots__ = ("fast", "slow", "signal")

    def __init__(self) -> None:
        super().__init__()
        self.fast = EMA()
        self.slow = EMA()
        self.signal = EMA()

    def update(self, ctx, source, fast_length, slow_length, signal_length):
        fast = self.fast.update(ctx, source, fast_length)
        slow = self.slow.update(ctx, source, slow_length)
        if is_na(fast) or is_na(slow):
            # The signal EMA must still advance or it would be `signal_length`
            # bars late for the rest of the run.
            self.signal.update(ctx, NA, signal_length)
            return (NA, NA, NA)
        macd = fast - slow
        signal = self.signal.update(ctx, macd, signal_length)
        histogram = NA if is_na(signal) else macd - signal
        return (macd, signal, histogram)


class BollingerBands(Indicator):
    """Returns ``[middle, upper, lower]``."""

    __slots__ = ("sma", "stdev")

    def __init__(self) -> None:
        super().__init__()
        self.sma = SMA()
        self.stdev = Stdev()

    def update(self, ctx, source, length, mult):
        middle = self.sma.update(ctx, source, length)
        deviation = self.stdev.update(ctx, source, length)
        if is_na(middle) or is_na(deviation):
            return (NA, NA, NA)
        offset = _dec(mult) * deviation
        return (middle, middle + offset, middle - offset)


class BBW(BollingerBands):
    def update(self, ctx, source, length, mult):
        middle, upper, lower = super().update(ctx, source, length, mult)
        if is_na(middle) or middle == ZERO:
            return NA
        return (upper - lower) / middle


class Stoch(Indicator):
    __slots__ = ("highs", "lows")

    def __init__(self) -> None:
        super().__init__()
        self.highs: deque[Decimal] | None = None
        self.lows: deque[Decimal] | None = None

    def update(self, ctx, source, high, low, length):
        n = self._fix_length(length)
        if self.highs is None:
            self.highs = deque(maxlen=n)
            self.lows = deque(maxlen=n)
        value, high_v, low_v = _dec(source), _dec(high), _dec(low)
        if is_na(value) or is_na(high_v) or is_na(low_v):
            return NA
        self.highs.append(high_v)
        self.lows.append(low_v)
        if len(self.highs) < n:
            return NA
        top, bottom = max(self.highs), min(self.lows)
        if top == bottom:
            return ZERO
        return HUNDRED * (value - bottom) / (top - bottom)


class CCI(Indicator):
    __slots__ = ("win",)

    def __init__(self) -> None:
        super().__init__()
        self.win: _Window | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.win is None:
            self.win = _Window(n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.win.push(value)
        if not self.win.full:
            return NA
        mean = self.win.mean()
        deviation = sum((abs(item - mean) for item in self.win.buf), ZERO) / Decimal(n)
        if deviation == ZERO:
            return ZERO
        return (value - mean) / (Decimal("0.015") * deviation)


# --- extremes and counters --------------------------------------------------


class _Extreme(Indicator):
    """Shared body for ``highest``/``lowest``/``highestbars``/``lowestbars``."""

    __slots__ = ("buf",)

    pick = staticmethod(max)
    want_bars = False

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque[Decimal] | None = None

    def update(self, ctx, source, length=None):
        # `ta.highest(20)` with one argument reads `high`; `ta.lowest(20)` reads
        # `low`. Pine's own shorthand, and scripts use it constantly.
        if length is None:
            length = source
            source = ctx.builtin("high" if self.pick is max else "low")
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.buf.append(value)
        if len(self.buf) < n:
            return NA
        best = self.pick(self.buf)
        if not self.want_bars:
            return best
        # Negative, and the most recent occurrence wins — Pine's convention.
        for offset, item in enumerate(reversed(self.buf)):
            if item == best:
                return -offset
        return NA


class Highest(_Extreme):
    pick = staticmethod(max)


class Lowest(_Extreme):
    pick = staticmethod(min)


class HighestBars(_Extreme):
    pick = staticmethod(max)
    want_bars = True


class LowestBars(_Extreme):
    pick = staticmethod(min)
    want_bars = True


class BarsSince(Indicator):
    """Bars since ``condition`` was last true; ``na`` until it has been."""

    __slots__ = ("count",)

    def __init__(self) -> None:
        super().__init__()
        self.count = NA

    def update(self, ctx, condition):
        if bool(condition) and not is_na(condition):
            self.count = 0
        elif not is_na(self.count):
            self.count += 1
        return self.count


class ValueWhen(Indicator):
    """``source`` the n-th most recent time ``condition`` was true."""

    __slots__ = ("hits",)

    #: Bounded like everything else here. Twenty is far past what a strategy
    #: reasonably asks for and keeps a year-long run from accumulating.
    MAX_OCCURRENCES = 20

    def __init__(self) -> None:
        super().__init__()
        self.hits: deque = deque(maxlen=self.MAX_OCCURRENCES)

    def update(self, ctx, condition, source, occurrence=0):
        if bool(condition) and not is_na(condition):
            self.hits.appendleft(_dec(source))
        index = _int(occurrence, "occurrence")
        if index >= len(self.hits):
            return NA
        return self.hits[index]


class Cum(Indicator):
    __slots__ = ("total",)

    def __init__(self) -> None:
        super().__init__()
        self.total = ZERO

    def update(self, ctx, source):
        value = _dec(source)
        if not is_na(value):
            self.total += value
        return self.total


class Sum(Indicator):
    __slots__ = ("win",)

    def __init__(self) -> None:
        super().__init__()
        self.win: _Window | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.win is None:
            self.win = _Window(n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.win.push(value)
        return self.win.total if self.win.full else NA


# --- crossings --------------------------------------------------------------


class _Crossing(Indicator):
    __slots__ = ("prev_a", "prev_b")

    def __init__(self) -> None:
        super().__init__()
        self.prev_a = NA
        self.prev_b = NA

    def _step(self, a, b):
        first, second = _dec(a), _dec(b)
        previous = (self.prev_a, self.prev_b)
        self.prev_a, self.prev_b = first, second
        if is_na(first) or is_na(second) or is_na(previous[0]) or is_na(previous[1]):
            return None
        return previous[0], previous[1], first, second


class Crossover(_Crossing):
    def update(self, ctx, a, b):
        step = self._step(a, b)
        if step is None:
            return False
        prev_a, prev_b, now_a, now_b = step
        return prev_a <= prev_b and now_a > now_b


class Crossunder(_Crossing):
    def update(self, ctx, a, b):
        step = self._step(a, b)
        if step is None:
            return False
        prev_a, prev_b, now_a, now_b = step
        return prev_a >= prev_b and now_a < now_b


class Cross(_Crossing):
    def update(self, ctx, a, b):
        step = self._step(a, b)
        if step is None:
            return False
        prev_a, prev_b, now_a, now_b = step
        return (prev_a <= prev_b and now_a > now_b) or (prev_a >= prev_b and now_a < now_b)


# --- shape ------------------------------------------------------------------


class _Direction(Indicator):
    """``rising``/``falling``: monotonic over the last ``length`` steps."""

    __slots__ = ("buf",)

    ascending = True

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque[Decimal] | None = None

    def update(self, ctx, source, length):
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n + 1)
        value = _dec(source)
        if is_na(value):
            return False
        self.buf.append(value)
        if len(self.buf) < n + 1:
            return False
        pairs = zip(list(self.buf)[:-1], list(self.buf)[1:], strict=True)
        if self.ascending:
            return all(later > earlier for earlier, later in pairs)
        return all(later < earlier for earlier, later in pairs)


class Rising(_Direction):
    ascending = True


class Falling(_Direction):
    ascending = False


class _Pivot(Indicator):
    """``pivothigh``/``pivotlow``: confirmed ``right`` bars after the fact.

    Deliberately late, and that is the point — a pivot is only a pivot once the
    bars to its right exist. Anything that claims one earlier is repainting.
    """

    __slots__ = ("buf", "left", "right")

    highest = True

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque[Decimal] | None = None
        self.left = 0
        self.right = 0

    def update(self, ctx, source, left=None, right=None):
        if right is None:
            # `ta.pivothigh(left, right)` — the two-argument form reads high/low.
            left, right = source, left
            source = ctx.builtin("high" if self.highest else "low")
        if self.buf is None:
            self.left = _int(left, "leftbars")
            self.right = _int(right, "rightbars")
            self.buf = deque(maxlen=self.left + self.right + 1)
        value = _dec(source)
        if is_na(value):
            return NA
        self.buf.append(value)
        if len(self.buf) < self.buf.maxlen:
            return NA
        window = list(self.buf)
        candidate = window[self.left]
        others = window[: self.left] + window[self.left + 1 :]
        if self.highest:
            return candidate if all(candidate > item for item in others) else NA
        return candidate if all(candidate < item for item in others) else NA


class PivotHigh(_Pivot):
    highest = True


class PivotLow(_Pivot):
    highest = False


# --- regression and percentile ----------------------------------------------


class LinReg(Indicator):
    """Least-squares fit over the window, read at ``length - 1 - offset``."""

    __slots__ = ("buf",)

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque[Decimal] | None = None

    def update(self, ctx, source, length, offset=0):
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.buf.append(value)
        if len(self.buf) < n:
            return NA
        count = Decimal(n)
        sum_x = Decimal(n * (n - 1) // 2)
        sum_x2 = Decimal(sum(index * index for index in range(n)))
        sum_y = ZERO
        sum_xy = ZERO
        for index, item in enumerate(self.buf):
            sum_y += item
            sum_xy += Decimal(index) * item
        denominator = count * sum_x2 - sum_x * sum_x
        if denominator == ZERO:
            return NA
        slope = (count * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / count
        return intercept + slope * (Decimal(n - 1) - Decimal(_int(offset, "offset")))


class PercentileLinearInterpolation(Indicator):
    __slots__ = ("buf",)

    def __init__(self) -> None:
        super().__init__()
        self.buf: deque[Decimal] | None = None

    def update(self, ctx, source, length, percentage):
        n = self._fix_length(length)
        if self.buf is None:
            self.buf = deque(maxlen=n)
        value = _dec(source)
        if is_na(value):
            return NA
        self.buf.append(value)
        if len(self.buf) < n:
            return NA
        ordered = sorted(self.buf)
        position = _dec(percentage) / HUNDRED * Decimal(n - 1)
        lower = int(position)
        upper = min(lower + 1, n - 1)
        weight = position - Decimal(lower)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


# --- registry ---------------------------------------------------------------

#: Name → factory. The runtime creates one object per ``(call_id, call path)``.
FACTORIES: dict[str, type[Indicator]] = {
    "sma": SMA,
    "ema": EMA,
    "rma": RMA,
    "wma": WMA,
    "vwma": VWMA,
    "hma": HMA,
    "stdev": Stdev,
    "variance": Variance,
    "rsi": RSI,
    "atr": ATR,
    "tr": TrueRange,
    "macd": MACD,
    "bb": BollingerBands,
    "bbw": BBW,
    "stoch": Stoch,
    "cci": CCI,
    "mom": Change,
    "roc": ROC,
    "crossover": Crossover,
    "crossunder": Crossunder,
    "cross": Cross,
    "change": Change,
    "highest": Highest,
    "lowest": Lowest,
    "highestbars": HighestBars,
    "lowestbars": LowestBars,
    "barssince": BarsSince,
    "valuewhen": ValueWhen,
    "cum": Cum,
    "sum": Sum,
    "percentile_linear_interpolation": PercentileLinearInterpolation,
    "linreg": LinReg,
    "rising": Rising,
    "falling": Falling,
    "pivothigh": PivotHigh,
    "pivotlow": PivotLow,
}

#: Indicators returning more than one value, so the runtime knows a tuple is a
#: tuple rather than one opaque value that happens to be iterable.
TUPLE_RESULTS = frozenset({"macd", "bb"})
