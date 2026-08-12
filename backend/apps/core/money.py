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
