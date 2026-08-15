"""Spec §4 — the per-leg deadline and independent failure handling.

These are the tests the platform exists for. If one of them regresses, one
partner's outage starts costing other partners money.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import pytest
from django.conf import settings
from django.test import override_settings

from apps.core.money import D
from apps.engine.executor import (
    TradeIntent,
    amend_sltp,
    close_trade,
    failure_notifications,
    open_trade,
)
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
    # A short explicit timeout keeps this test quick; the configured deadline
    # is covered by test_the_whole_fanout_fits_the_configured_budget.
    result = await open_trade(accounts, intent(), timeout=1.0)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, "a hung account blocked the fan-out"
    assert len(result.succeeded) == 2
    assert result.failed[0].timed_out


async def test_the_whole_fanout_fits_the_configured_budget():
    """Spec §4: every leg dispatched within the configured deadline (Q19)."""
    accounts = [(i, PaperAdapter(balance=D("1000"), latency=0.02)) for i in range(25)]
    result = await open_trade(accounts, intent())

    assert result.all_ok
    assert result.within_budget(
        settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
    ), f"fan-out took {result.total_ms:.0f}ms"


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
    # The machine-readable code must survive the wrap in _make_open — the UI
    # distinguishes "too small to trade" from "the exchange broke" on it.
    assert result.failed[0].error_code == "below_min_qty"


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


@override_settings(
    TRADING={
        **__import__("django.conf", fromlist=["settings"]).settings.TRADING,
        "STOP_ALL": True,
    }
)
async def test_stop_all_never_blocks_an_amend_either():
    """G1 / Q14: tightening a stop on a live position is a protection action.

    The panel's copy promises amends keep working while halted. Before this,
    ``amend_sltp`` fanned out with the default ``respect_stop_all=True`` and the
    admin got a 500 with an unhandled StopAllActive traceback.
    """
    adapter = PaperAdapter(balance=D("1000"))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.05"),
        order_type=OrderType.MARKET,
    )

    result = await amend_sltp(
        [(1, adapter)],
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        admin_entry=D("100000"),
    )

    assert result.all_ok, [leg.error for leg in result.failed]
    assert adapter.sltp != (None, None)


# --- Q5d: SL/TP amends must not stack conditional orders (G2) ---------------


class StackingAdapter(PaperAdapter):
    """An exchange that cannot amend SL/TP in place — the other six.

    ``set_sltp`` only ever *places*, exactly like Binance/OKX/KuCoin/Gate.io/
    Hyperliquid, so the platform is what has to take the old orders away.
    """

    capabilities = replace(PaperAdapter.capabilities, native_sltp_amend=False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.live: list[str] = []
        self.trace: list[str] = []
        self._next = 0

    async def set_sltp(self, *, symbol, stop_loss, take_profit) -> None:
        await super().set_sltp(symbol=symbol, stop_loss=stop_loss, take_profit=take_profit)
        self._next += 1
        self.live.append(f"stop-{self._next}")
        self.trace.append("place")

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        self.trace.append("list")
        return list(self.live)

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        self.trace.append("cancel")
        self.live = [order for order in self.live if order not in order_ids]


async def amend(adapter, sl="0.5"):
    return await amend_sltp(
        [(1, adapter)],
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        sl_pct=D(sl),
        tp_pct=D("1"),
        admin_entry=D("100000"),
    )


async def stacked_adapter() -> StackingAdapter:
    adapter = StackingAdapter(balance=D("1000"))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.05"),
        order_type=OrderType.MARKET,
    )
    return adapter


async def test_an_amend_leaves_exactly_one_pair_of_stops_alive():
    """G2: the position must never carry the stop the admin just replaced.

    Two live stops means whichever triggers first wins — possibly the old price.
    """
    adapter = await stacked_adapter()

    for percent in ("0.5", "0.8", "1.2"):
        assert (await amend(adapter, percent)).all_ok

    assert adapter.live == ["stop-3"], f"stale stops left live: {adapter.live}"


async def test_place_then_cancel_places_before_it_cancels():
    """Q5d's answer: overlap on the safe side. The old stop is removed only
    once the new one exists, so there is no unprotected moment."""
    adapter = await stacked_adapter()
    await amend(adapter)
    adapter.trace.clear()

    await amend(adapter)

    assert adapter.trace == ["list", "place", "cancel"]


@override_settings(
    TRADING={
        **__import__("django.conf", fromlist=["settings"]).settings.TRADING,
        "SLTP_AMEND_STRATEGY": "cancel_then_place",
    }
)
async def test_cancel_then_place_is_a_real_branch_not_dead_config():
    """The other half of Q5d: the setting has to actually change behaviour."""
    adapter = await stacked_adapter()
    await amend(adapter)
    adapter.trace.clear()

    await amend(adapter)

    assert adapter.trace == ["list", "cancel", "place"]
    assert adapter.live == ["stop-2"]


async def test_an_exchange_that_amends_in_place_is_left_alone():
    """Bybit and the paper adapter replace SL/TP in one call — no cancel dance."""
    adapter = PaperAdapter(balance=D("1000"))
    assert adapter.capabilities.native_sltp_amend

    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.05"),
        order_type=OrderType.MARKET,
    )
    await amend(adapter)

    assert "list_conditional_orders" not in adapter.calls


async def test_the_first_attach_after_entry_also_clears_a_half_placed_pair():
    """Q5e retries the attach. Without the snapshot, attempt two would stack on
    whatever attempt one managed to place before it failed."""
    adapter = StackingAdapter(balance=D("1000"))
    adapter.capabilities = replace(adapter.capabilities, native_sltp_on_entry=False)
    result = await open_trade([(1, adapter)], intent())

    assert result.all_ok
    assert len(adapter.live) == 1


# --- Spec §4: identical leverage (G6) ---------------------------------------


async def test_an_account_capped_below_the_asked_leverage_sits_out():
    """Spec §4 says every account runs the same leverage. An account whose
    exchange caps it lower cannot comply, so it is skipped with a notification
    — the spec §5 treatment — rather than silently trading a different size."""
    capped = PaperAdapter(balance=D("1000"))
    capped.capabilities = replace(capped.capabilities, max_leverage=5)
    accounts = [(1, PaperAdapter(balance=D("1000"))), (2, capped)]

    result = await open_trade(accounts, intent(leverage=10))

    assert [leg.account_id for leg in result.succeeded] == [1]
    assert result.failed[0].error_code == "leverage_capped"
    assert await capped.get_position("BTCUSDT") is None
    assert failure_notifications(result)[0]["persistent"] is True


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
