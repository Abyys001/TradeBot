"""questions.md Q5a — the two readings, in numbers."""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.core.money import D
from apps.exchanges.base import Side
from apps.trading.sltp import (
    SLTPRejection,
    compare_bases,
    liquidation_price,
    pct_from_drag,
    resolve_active,
)

# The worked example from questions.md Q5a: $1,000 account, 10x, BTC at 100k.
CASE = dict(
    side=Side.LONG,
    entry=D("100000"),
    leverage=10,
    margin=D("990"),
    notional=D("9900"),
)


def test_the_two_readings_differ_by_exactly_the_leverage():
    """The Q5a table, asserted. A 2% price stop costs 10x a 2% margin stop."""
    lines = compare_bases(**CASE, sl_pct=D("2"), tp_pct=None)
    assert lines["price"].price_move_pct == D("2")
    assert lines["margin"].price_move_pct == D("0.2")
    assert lines["price"].stop_price == D("98000")
    assert lines["margin"].stop_price == D("99800")
    assert lines["price"].loss_at_stop == D("198")  # 2% of 9900 notional
    assert lines["margin"].loss_at_stop == D("19.8")
    assert lines["price"].loss_at_stop == lines["margin"].loss_at_stop * 10


def test_a_two_percent_price_stop_costs_a_fifth_of_the_account():
    """Why Q5a matters: a small-sounding percentage is not a small loss."""
    lines = compare_bases(**CASE, sl_pct=D("2"), tp_pct=None)
    assert lines["price"].loss_pct_of_account == D("19.8")
    assert lines["margin"].loss_pct_of_account == D("1.98")


def test_a_price_stop_beyond_the_liquidation_distance_can_never_trigger():
    """At 10x, liquidation is 10% away, so a 12% price stop is unreachable."""
    lines = compare_bases(**CASE, sl_pct=D("12"), tp_pct=None)
    assert lines["price"].reachable is False
    assert "liquidation" in lines["price"].note
    # Read as margin, the same 12% is a 1.2% price move — well inside.
    assert lines["margin"].reachable is True


def test_liquidation_distance_is_one_over_leverage():
    """It depends on leverage alone, not on how much margin is committed."""
    assert liquidation_price(Side.LONG, D("100000"), 10) == D("90000")  # 10% away
    assert liquidation_price(Side.LONG, D("100000"), 5) == D("80000")  # 20% away
    assert liquidation_price(Side.SHORT, D("100000"), 10) == D("110000")


def test_short_side_mirrors_the_stop_direction():
    lines = compare_bases(
        side=Side.SHORT,
        entry=D("100000"),
        leverage=10,
        margin=D("990"),
        notional=D("9900"),
        sl_pct=D("0.5"),
        tp_pct=D("1"),
    )
    price = lines["price"]
    assert price.stop_price > D("100000")  # a short loses when price rises
    assert price.take_profit_price < D("100000")


@override_settings(
    TRADING={
        **__import__("django.conf", fromlist=["settings"]).settings.TRADING,
        "REJECT_SL_BEYOND_LIQUIDATION": True,
        "SLTP_BASIS": "price",
    }
)
def test_guard_refuses_a_stop_beyond_liquidation():
    with pytest.raises(SLTPRejection) as exc:
        resolve_active(**CASE, sl_pct=D("50"), tp_pct=None)
    assert exc.value.code == "sl_beyond_liquidation"


def test_chart_drag_round_trips_to_a_percentage():
    """Q5c: dragging to 98,000 on a long entered at 100,000 is a 2% stop."""
    pct = pct_from_drag(
        side=Side.LONG, admin_entry=D("100000"), dragged_price=D("98000"), leverage=10
    )
    assert pct == D("2")
    resolved = compare_bases(**CASE, sl_pct=pct, tp_pct=None)["price"]
    assert resolved.stop_price == D("98000")
