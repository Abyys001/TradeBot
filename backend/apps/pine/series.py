"""``na`` and ``Series`` — the two value primitives every indicator sits on.

**``na`` is a first-class value, not ``None`` and not a ``NaN`` by accident.**
That distinction is worth a module of its own because getting it wrong produces
the worst failure mode available: an indicator that is silently correct for two
hundred bars and then wrong once. Arithmetic on ``na`` yields ``na``; *every*
comparison with ``na`` — ``==`` included — yields ``False``. So a warm-up bug
does not raise, it looks exactly like a strategy that politely does not trade
for a while, which is why ``na()`` is the only way to test for it and why
``ta.*`` warm-up has golden tests.

**``Series`` is bounded.** A bot on 1m bars runs 525,600 of them a year; an
unbounded list is a slow leak with a memory alarm at the end of it. The buffer
holds ``depth`` bars and drops the oldest, amortised O(1) on both push and
``[n]``.

Neither type is frozen: these are exactly the objects the engine accumulates
into (``bot-plan.md`` §1.6).
"""

from __future__ import annotations

from decimal import Decimal


class _Na:
    """The ``na`` singleton. Use ``value is NA``; ``==`` deliberately says False."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "na"

    def __bool__(self) -> bool:
        return False

    # Arithmetic propagates. Both directions, so `close + na` and `na + close`
    # behave the same however Python happens to dispatch them.
    def _propagate(self, *_args):
        return self

    __add__ = __radd__ = _propagate
    __sub__ = __rsub__ = _propagate
    __mul__ = __rmul__ = _propagate
    __truediv__ = __rtruediv__ = _propagate
    __mod__ = __rmod__ = _propagate
    __pow__ = __rpow__ = _propagate
    __neg__ = __pos__ = __abs__ = _propagate

    # Comparison yields False, never na and never an exception. This is Pine's
    # behaviour and it is the reason `ta.rsi(close, 14) > 70` is quietly false
    # during warm-up instead of raising.
    def _false(self, *_args) -> bool:
        return False

    __lt__ = __le__ = __gt__ = __ge__ = __eq__ = __ne__ = _false

    def __hash__(self) -> int:
        return hash("__pine_na__")


NA = _Na()


def is_na(value) -> bool:
    return value is NA


def nz(value, replacement=None):
    """``na`` becomes ``replacement`` (default 0). Pine's own ``nz``."""
    if value is NA:
        return Decimal("0") if replacement is None else replacement
    return value


class Series:
    """A value per bar, with ``[n]`` reaching back. Index 0 is the current bar."""

    __slots__ = ("_buf", "_depth")

    def __init__(self, depth: int = 5000) -> None:
        self._buf: list = []
        self._depth = max(2, depth)

    def push(self, value) -> None:
        self._buf.append(value)
        # Trimmed in blocks rather than per push: one slice every `depth` bars
        # instead of a list shuffle on every one of them.
        if len(self._buf) > self._depth * 2:
            del self._buf[: len(self._buf) - self._depth]

    def set(self, value) -> None:
        """Overwrite the current bar's value — what ``x := 1`` does mid-bar."""
        if self._buf:
            self._buf[-1] = value
        else:
            self._buf.append(value)

    def __getitem__(self, offset: int):
        if offset < 0:
            # Pine has no forward reference and neither does this. A negative
            # offset would be a look-ahead, which is the one bug a backtest
            # cannot detect in itself.
            raise IndexError("a series cannot be read forward")
        if offset >= len(self._buf):
            return NA
        return self._buf[-1 - offset]

    def __len__(self) -> int:
        return len(self._buf)

    @property
    def value(self):
        return self._buf[-1] if self._buf else NA

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Series({self.value!r}, depth={len(self._buf)})"
