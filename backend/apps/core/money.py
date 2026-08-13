"""Decimal helpers. Money never touches float in this codebase."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_UP, Decimal, InvalidOperation

ZERO = Decimal("0")


def D(value) -> Decimal:  # noqa: N802 - deliberately terse, used everywhere
    """Coerce to Decimal via str so float artefacts never enter the system."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"not a usable decimal: {value!r}") from exc


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Round down to a multiple of ``step``.

    Always down: rounding a position size up could exceed the balance fraction
    the admin authorised (spec §5) and get the order rejected for margin.
    """
    if step <= ZERO:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= ZERO:
        return value
    return (value / step).to_integral_value(rounding=ROUND_UP) * step


def quantize_price(price: Decimal, tick: Decimal) -> Decimal:
    """Snap a price to the exchange tick grid (round down; direction-neutral)."""
    return floor_to_step(price, tick)


def pct(value: Decimal, percent: Decimal) -> Decimal:
    return value * percent / Decimal("100")


def human(value, *, min_dp: int = 1, sig: int = 4) -> str:
    """A decimal a person can read: one place, and more only when one would lie.

    Stored money is 8dp and a division is 28 — both true and both unreadable in
    a sentence ("99% of 10.00000000 USDT ... 0.0000990000 BTCUSDT"). This keeps
    ``sig`` significant digits, never fewer than ``min_dp`` decimals, and drops
    the zeros that carry no information::

        10        -> "10.0"      49.5   -> "49.5"
        0.000099  -> "0.000099"  0.001  -> "0.001"

    Always rounds **down**, like every other size in this codebase: a rejection
    notice that rounds a size up reads as if the account nearly qualified.
    """
    number = D(value)
    if number == 0:
        return f"{ZERO:.{min_dp}f}" if min_dp else "0"
    places = max(min_dp, sig - 1 - number.adjusted())
    text = f"{number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_DOWN):f}"
    if "." not in text:
        return text
    whole, _, fraction = text.rstrip("0").partition(".")
    fraction = fraction.ljust(min_dp, "0")
    return f"{whole}.{fraction}" if fraction else whole
