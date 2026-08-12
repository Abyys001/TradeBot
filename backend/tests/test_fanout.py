"""Spec §4 — the 1-second budget and independent failure handling.

These are the tests the platform exists for. If one of them regresses, one
partner's outage starts costing other partners money.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import pytest
from django.test import override_settings

from apps.core.money import D
from apps.engine.executor import TradeIntent, close_trade, failure_notifications, open_trade
from apps.engine.fanout import StopAllActive, fan_out
from apps.exchanges.base import MarketType, OrderType, Side
from apps.exchanges.paper import PaperAdapter

pytestmark = pytest.mark.asyncio


def intent(**overrides) -> TradeIntent:
    base = dict(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.2"),
        tp_pct=D("0.4"),
        limit_price=D("100000"),
    )
    return TradeIntent(**{**base, **overrides})


async def test_one_failing_account_does_not_stop_the_others():
    """Spec §4: independent failure handling."""
    accounts = [
        (1, PaperAdapter(balance=D("1000"))),
        (2, PaperAdapter(balance=D("1000"), fail_on={"place_order"})),
        (3, PaperAdapter(balance=D("1000"))),
    ]
    result = await open_trade(accounts, intent())

    assert len(result.succeeded) == 2
    assert len(result.failed) == 1
    assert result.failed[0].account_id == 2
    assert {leg.account_id for leg in result.succeeded} == {1, 3}


async def test_a_hung_account_is_abandoned_not_awaited():
    """A dead exchange must not drag the whole fan-out past the deadline."""
    accounts = [
        (1, PaperAdapter(balance=D("1000"))),
        (2, PaperAdapter(balance=D("1000"), latency=5.0)),  # hangs
        (3, PaperAdapter(balance=D("1000"))),
    ]
    started = time.perf_counter()
    result = await open_trade(accounts, intent())
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, "a hung account blocked the fan-out"
    assert len(result.succeeded) == 2
    assert result.failed[0].timed_out


async def test_the_whole_fanout_fits_the_one_second_budget():
    """Spec §4: every leg dispatched within ~1s of the others."""
    accounts = [(i, PaperAdapter(balance=D("1000"), latency=0.02)) for i in range(25)]
    result = await open_trade(accounts, intent())

    assert result.all_ok
    assert result.within_budget(1.0), f"fan-out took {result.total_ms:.0f}ms"


async def test_legs_run_concurrently_not_serially():
    """25 accounts x 60ms of latency is 1.5s serial, well under 1s concurrent."""
    accounts = [(i, PaperAdapter(balance=D("1000"), latency=0.06)) for i in range(25)]
    result = await open_trade(accounts, intent())

    assert result.all_ok
    assert result.total_ms < 1000


async def test_a_too_small_account_sits_out_and_the_rest_trade():
    """Spec §5: below minimum notional -> skip that account only."""
    accounts = [
        (1, PaperAdapter(balance=D("1000"))),
        (2, PaperAdapter(balance=D("0.01"))),  # 99% of a cent
        (3, PaperAdapter(balance=D("500"))),
    ]
    result = await open_trade(accounts, intent())

    assert {leg.account_id for leg in result.succeeded} == {1, 3}
    assert result.failed[0].account_id == 2


async def test_every_failure_produces_a_persistent_notification():
    """Spec §4: it stays until the admin dismisses it."""
    accounts = [
        (1, PaperAdapter(balance=D("1000"))),
        (2, PaperAdapter(balance=D("1000"), fail_on={"place_order"})),
    ]
    result = await open_trade(accounts, intent())
    notifications = failure_notifications(result)

    assert len(notifications) == 1
    assert notifications[0]["account_id"] == 2
    assert notifications[0]["persistent"] is True


async def test_sizing_differs_per_account_but_leverage_does_not():
    """Spec §4/§5: same leverage and SL/TP %, different dollar size."""
    accounts = [
        (1, PaperAdapter(balance=D("1000"))),
        (2, PaperAdapter(balance=D("5000"))),
    ]
    result = await open_trade(accounts, intent())

    small, large = (leg.value for leg in sorted(result.succeeded, key=lambda x: x.account_id))
    assert large.qty > small.qty
    assert large.margin == small.margin * 5
    assert small.stop_loss == large.stop_loss  # same % off the same entry price


@override_settings(
    TRADING={
        **__import__("django.conf", fromlist=["settings"]).settings.TRADING,
        "STOP_ALL": True,
    }
)
async def test_stop_all_blocks_new_orders_but_never_blocks_closing():
    """Spec §7: the kill switch must not trap the admin in open positions."""
    accounts = [(1, PaperAdapter(balance=D("1000")))]

    with pytest.raises(StopAllActive):
        await open_trade(accounts, intent())

    # Open one with the switch off so there is something to close.
    adapter = PaperAdapter(balance=D("1000"))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.05"),
        order_type=OrderType.MARKET,
    )
    result = await close_trade([(1, adapter)], symbol="BTCUSDT")
    assert result.all_ok


async def test_an_adapter_that_raises_outside_the_contract_is_still_contained():
    async def explode():
        raise RuntimeError("adapter bug")

    async def fine():
        return "ok"

    result = await fan_out([(1, fine), (2, explode), (3, fine)])
    assert len(result.succeeded) == 2
    assert result.failed[0].error_code == "RuntimeError"


async def test_concurrent_fanouts_do_not_interfere():
    """Two admin actions in flight at once keep their legs separate."""
    a = [(i, PaperAdapter(balance=D("1000"), latency=0.05)) for i in range(5)]
    b = [(i + 100, PaperAdapter(balance=D("1000"), latency=0.05)) for i in range(5)]

    ra, rb = await asyncio.gather(open_trade(a, intent()), open_trade(b, intent()))

    assert ra.all_ok and rb.all_ok
    assert {leg.account_id for leg in ra.legs}.isdisjoint({leg.account_id for leg in rb.legs})


async def test_adapter_error_from_one_leg_never_leaks_out_of_fan_out():
    accounts = [(1, PaperAdapter(balance=D("1000"), fail_on={"get_balance"}))]
    result = await open_trade(accounts, intent())
    assert result.failed and isinstance(result.failed[0].error, str)
    assert not result.succeeded


async def test_close_position_fans_out_to_everyone():
    adapters = [PaperAdapter(balance=D("1000")) for _ in range(3)]
    accounts = list(enumerate(adapters))
    await open_trade(accounts, intent())

    result = await close_trade(accounts, symbol="BTCUSDT")
    assert result.all_ok
    for adapter in adapters:
        assert await adapter.get_position("BTCUSDT") is None


async def test_sltp_failure_closes_the_position_under_the_default_policy():
    """Q5e default: never leave a leveraged position unprotected."""
    adapter = PaperAdapter(balance=D("1000"), fail_on={"set_sltp"})
    # Force the post-entry attach path, as on exchanges without native entry SL/TP.
    adapter.capabilities = replace(adapter.capabilities, native_sltp_on_entry=False)
    result = await open_trade([(1, adapter)], intent())

    assert not result.succeeded
    assert "closed at market" in result.failed[0].error
    assert await adapter.get_position("BTCUSDT") is None
