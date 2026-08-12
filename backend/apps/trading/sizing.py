"""Position sizing (spec §5, questions.md Q4 / Q12).

Decided rule: margin = BALANCE_FRACTION (0.99) of the account's available USDT
balance, with leverage multiplying on top. Notional = margin x leverage.

Not the other reading — 99% as *notional* — because the admin confirmed
leverage is used continuously and 99% of each account is committed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from apps.core.money import D, floor_to_step
from apps.exchanges.base import Balance, MarketType, SymbolRules


class SizingRejection(Exception):
    """This account cannot take the trade. Never a reason to abort the others."""

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True, slots=True)
class SizedOrder:
    qty: Decimal
    margin: Decimal
    notional: Decimal
    price: Decimal
    leverage: int


def balance_fraction() -> Decimal:
    return D(settings.TRADING["BALANCE_FRACTION"])


def size_order(
    *,
    balance: Balance,
    price: Decimal,
    leverage: int,
    rules: SymbolRules,
    market: MarketType = MarketType.FUTURES,
) -> SizedOrder:
    """Size one account's leg. Raises SizingRejection when this account sits out.

    Spot ignores leverage (Q4: same 99% rule, no multiplier).
    """
    if not balance.is_usdt:
        # Q4: report it on the dashboard, do not trade it.
        raise SizingRejection(
            f"account balance is {balance.asset}, not USDT", code="non_usdt_balance"
        )

    price = D(price)
    if price <= 0:
        raise SizingRejection("no usable mark price", code="no_price")

    effective_leverage = 1 if market is MarketType.SPOT else int(leverage)
    if effective_leverage < 1:
        raise SizingRejection("leverage must be at least 1", code="bad_leverage")

    margin = D(balance.available) * balance_fraction()
    notional = margin * D(effective_leverage)

    raw_qty = notional / price
    qty = floor_to_step(raw_qty, rules.qty_step)

    # Never round up past the authorised fraction (spec §5): rounding down can
    # push a marginal account below the exchange minimum, and that is correct —
    # it sits out with a notification rather than over-committing.
    if qty < rules.min_qty:
        raise SizingRejection(
            f"size {qty} is below the exchange minimum quantity {rules.min_qty}",
            code="below_min_qty",
        )
    if qty * price < rules.min_notional:
        raise SizingRejection(
            f"notional {qty * price} is below the exchange minimum "
            f"{rules.min_notional}",
            code="below_min_notional",
        )

    return SizedOrder(
        qty=qty,
        margin=margin,
        notional=qty * price,
        price=price,
        leverage=effective_leverage,
    )
