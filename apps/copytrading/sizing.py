"""Pure helpers for copy-trade position sizing and high-water-mark fees.

Kept free of DB/network so they are trivially unit-testable and reused by the
fan-out task in ``tasks.py``.
"""
from __future__ import annotations

from decimal import Decimal

from .models import Subscription


def compute_size(
    *,
    balance: float,
    price: float,
    sizing_mode: str,
    risk_pct: Decimal | float,
    fixed_notional: Decimal | float,
    leverage: int,
) -> float:
    """Return the base-asset quantity to trade for one investor.

    ``risk_pct`` mode sizes a fraction of the investor's own balance;
    ``fixed_notional`` sizes a constant quote-currency notional. Both scale by
    leverage. Returns 0.0 when inputs make a real order impossible.
    """
    price = float(price)
    if price <= 0 or leverage <= 0:
        return 0.0

    if sizing_mode == Subscription.Sizing.FIXED_NOTIONAL:
        notional = float(fixed_notional)
    else:
        notional = float(balance) * (float(risk_pct) / 100.0)

    notional *= leverage
    if notional <= 0:
        return 0.0
    return notional / price


def realized_pnl(*, entry_price: float, exit_price: float, size: float) -> float:
    """PnL of closing a signed position (``size`` > 0 long, < 0 short)."""
    return (float(exit_price) - float(entry_price)) * float(size)


def accrue_fee(
    *,
    prior_realized: Decimal | float,
    prior_hwm: Decimal | float,
    realized_delta: Decimal | float,
    fee_rate: Decimal | float,
) -> tuple[float, float, float]:
    """Apply one realized-PnL event under a high-water mark.

    Fee is charged only on profit that lifts cumulative realized PnL above its
    prior peak (the HWM). Losses lower cumulative PnL but never refund fees and
    never move the HWM down.

    Returns ``(fee_charged, new_realized, new_hwm)``.
    """
    new_realized = float(prior_realized) + float(realized_delta)
    hwm = float(prior_hwm)
    fee = 0.0
    if new_realized > hwm:
        fee = (new_realized - hwm) * float(fee_rate)
        hwm = new_realized
    return fee, new_realized, hwm
