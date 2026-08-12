"""Spec §5 / questions.md Q4, Q12."""

from __future__ import annotations

import pytest

from apps.core.money import D
from apps.exchanges.base import Balance, MarketType, SymbolRules
from apps.trading.sizing import SizingRejection, size_order

RULES = SymbolRules(
    symbol="BTCUSDT",
    price_tick=D("0.1"),
    qty_step=D("0.00001"),
    min_qty=D("0.00001"),
    min_notional=D("5"),
    max_leverage=10,
)


def usdt(amount: str) -> Balance:
    return Balance(asset="USDT", available=D(amount), total=D(amount))


@pytest.mark.parametrize(
    ("balance", "expected_margin"),
    [("10", "9.90"), ("50", "49.50"), ("100", "99.00")],
)
def test_ninety_nine_percent_of_each_account(balance, expected_margin):
    """The admin's worked example. Note $10 -> $9.90, not $9 (Q12)."""
    sized = size_order(
        balance=usdt(balance), price=D("100"), leverage=10, rules=RULES
    )
    assert sized.margin == D(expected_margin)


def test_margin_is_the_fraction_and_leverage_multiplies_on_top():
    """Q4: 99% is the *margin*, not the notional."""
    sized = size_order(balance=usdt("1000"), price=D("100"), leverage=10, rules=RULES)
    assert sized.margin == D("990")
    assert sized.notional == D("9900")  # not 990


def test_spot_ignores_leverage():
    sized = size_order(
        balance=usdt("1000"),
        price=D("100"),
        leverage=10,
        rules=RULES,
        market=MarketType.SPOT,
    )
    assert sized.margin == D("990")
    assert sized.notional == D("990")
    assert sized.leverage == 1


def test_quantity_rounds_down_never_up():
    coarse = SymbolRules(
        symbol="BTCUSDT",
        price_tick=D("0.1"),
        qty_step=D("0.001"),
        min_qty=D("0.001"),
        min_notional=D("5"),
        max_leverage=10,
    )
    sized = size_order(balance=usdt("1000"), price=D("100000"), leverage=10, rules=coarse)
    # 9900 / 100000 = 0.099 exactly on the step; a smaller balance must floor.
    assert sized.qty == D("0.099")
    smaller = size_order(balance=usdt("1007"), price=D("100000"), leverage=10, rules=coarse)
    assert smaller.qty == D("0.099")  # 0.0996... floored, never 0.1
    assert smaller.qty * D("100000") <= smaller.margin * 10


def test_non_usdt_balance_is_rejected_not_traded():
    """Q4: report it on the dashboard instead."""
    with pytest.raises(SizingRejection) as exc:
        size_order(
            balance=Balance(asset="BTC", available=D("1"), total=D("1")),
            price=D("100"),
            leverage=10,
            rules=RULES,
        )
    assert exc.value.code == "non_usdt_balance"


def test_below_minimum_notional_skips_the_account():
    """Spec §5: skip with a notification, never round up past 99%."""
    with pytest.raises(SizingRejection) as exc:
        size_order(balance=usdt("0.10"), price=D("100000"), leverage=1, rules=RULES)
    assert exc.value.code in {"below_min_qty", "below_min_notional"}
