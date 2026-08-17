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
    confirm_open,
    failure_notifications,
    open_trade,
)
from apps.engine.fanout import StopAllActive, fan_out
from apps.exchanges.base import (
    ExchangeUnavailable,
    MarketType,
    OrderType,
    Position,
    Side,
    SLTPState,
)
from apps.exchanges.paper import PaperAdapter
from apps.trading.services import SAT_OUT_CODES

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


# --- SL/TP read-back: the exchange is the only source of truth --------------
#
# ``get_sltp`` reads the resting protection back. "Attached" is only a real
# statement when the exchange confirms it; a silent drop — the missing take-
# profit this read-back exists to catch — must not read as a protected leg.


async def test_paper_read_back_confirms_sl_and_tp_on_entry():
    """Native entry attach is verified, not assumed from the fill's side effect."""
    adapter = PaperAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], intent())

    assert result.all_ok
    leg = result.succeeded[0]
    assert leg.value.sltp_attached is True
    assert leg.value.sltp_verified is True
    assert leg.value.stop_loss == adapter._state["sltp"][0]
    assert leg.value.take_profit == adapter._state["sltp"][1]


async def test_an_amend_reads_back_and_verifies_the_resting_prices():
    """The amend records the prices the exchange actually holds, not the ask."""
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

    assert result.all_ok
    value = result.succeeded[0].value
    assert value.attached is True
    assert value.verified is True
    assert value.stop_loss == adapter._state["sltp"][0]
    assert value.take_profit == adapter._state["sltp"][1]


class BadReadbackAdapter(PaperAdapter):
    """An exchange that holds a *different* SL/TP than the one placed."""

    async def get_sltp(self, symbol):
        state = await super().get_sltp(symbol)
        if state is None:
            return None
        return SLTPState(state.stop_loss + D("100"), state.take_profit + D("100"))


async def test_a_read_back_that_disagrees_fails_the_leg_and_closes():
    """A stop the exchange does not hold is a missing stop, not a placed one."""
    adapter = BadReadbackAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], intent())

    assert not result.succeeded
    assert "position closed at market" in result.failed[0].error
    assert await adapter.get_position("BTCUSDT") is None


class UnverifiableAdapter(PaperAdapter):
    """An exchange that cannot be read back (Toobit, LBank)."""

    async def get_sltp(self, symbol):
        return None


async def test_an_exchange_that_cannot_answer_is_unconfirmed_not_failed():
    """An unanswerable read-back is "cannot hold to account", not an alarm."""
    adapter = UnverifiableAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], intent())

    assert result.all_ok
    leg = result.succeeded[0]
    assert leg.value.sltp_attached is True
    assert leg.value.sltp_verified is False
    assert not failure_notifications(result)


# --- Q19: post-deadline reconciliation --------------------------------------
#
# ``asyncio.wait_for`` cancels a leg at the deadline, but cancellation cannot
# unsend a request the exchange already received. The exchange is the only
# source the platform trusts, so these adapters model it doing the *real* thing
# and then staying silent past the deadline — the exact behaviour that used to
# mint false "exceeded the deadline" failures.


class LateFillAdapter(PaperAdapter):
    """The entry lands on the exchange but the reply never reaches us in time."""

    async def place_order(self, **kwargs):
        await super().place_order(**kwargs)
        await asyncio.sleep(5.0)


async def test_a_timed_out_entry_that_filled_is_a_late_fill_not_a_failure():
    """Q19: never say "exceeded the deadline" about a position that exists."""
    adapter = LateFillAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], intent(), timeout=0.5)

    assert not result.failed
    assert not failure_notifications(result), "a confirmed fill is not a failure"
    assert await adapter.get_position("BTCUSDT") is not None
    leg = result.succeeded[0]
    assert leg.error_code == "late_fill"
    assert "confirmed on the exchange" in leg.error
    assert leg.value.qty == (await adapter.get_position("BTCUSDT")).size


async def test_a_timed_out_entry_that_never_filled_stays_a_timeout():
    """A hung account the exchange cannot confirm is abandoned, not fabricated."""
    result = await open_trade(
        [(1, PaperAdapter(balance=D("1000"), latency=5.0))], intent(), timeout=0.5
    )

    assert result.failed[0].timed_out
    assert failure_notifications(result)[0]["persistent"] is True


class EmulatedLateFillAdapter(LateFillAdapter):
    """A late fill on an exchange that attaches SL/TP *after* entry."""

    capabilities = replace(PaperAdapter.capabilities, native_sltp_on_entry=False)


async def test_a_late_fill_is_reprotected_when_native_entry_sltp_is_unavailable():
    """A confirmed fill is never left running at leverage without protection."""
    adapter = EmulatedLateFillAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], intent(), timeout=0.5)

    assert result.succeeded[0].error_code == "late_fill"
    assert result.succeeded[0].value.sltp_attached is True
    assert adapter._state["sltp"] != (None, None)


async def test_a_late_fill_that_cannot_be_protected_is_closed_not_left_unprotected():
    """Q5e default: no leveraged position is left without a stop."""
    adapter = EmulatedLateFillAdapter(balance=D("1000"), fail_on={"set_sltp"})
    result = await open_trade([(1, adapter)], intent(), timeout=0.5)

    assert not result.succeeded
    assert result.failed[0].error_code == "closed_after_late_fill"
    assert "closed at market" in result.failed[0].error
    assert await adapter.get_position("BTCUSDT") is None
    assert failure_notifications(result)[0]["persistent"] is True


class LateCloseAdapter(PaperAdapter):
    """The close actually flattens the position, but the reply is slow."""

    async def close_position(self, symbol):
        await super().close_position(symbol)
        await asyncio.sleep(5.0)


async def test_a_close_that_actually_happened_is_confirmed_not_failed():
    adapter = LateCloseAdapter(balance=D("1000"))
    adapter.set_mark_price(D("90000"))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.05"),
        order_type=OrderType.MARKET,
    )

    result = await close_trade([(1, adapter)], symbol="BTCUSDT", timeout=0.5)

    assert not result.failed
    assert not failure_notifications(result)
    assert await adapter.get_position("BTCUSDT") is None
    leg = result.succeeded[0]
    assert leg.error_code == "late_close"
    assert leg.value == D("90000")


class LateSltpAdapter(PaperAdapter):
    """The amend's set_sltp lands but never answers; the confirm re-apply is fast."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slow = True

    async def set_sltp(self, *, symbol, stop_loss, take_profit):
        await super().set_sltp(symbol=symbol, stop_loss=stop_loss, take_profit=take_profit)
        if self._slow:
            self._slow = False
            await asyncio.sleep(5.0)


async def test_an_amend_that_landed_is_reapplied_and_confirmed():
    adapter = LateSltpAdapter(balance=D("1000"))
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
        timeout=0.5,
    )

    assert not result.failed
    assert not failure_notifications(result)
    leg = result.succeeded[0]
    assert leg.error_code == "late_amend"
    assert "confirmed on the exchange" in leg.error
    assert adapter._state["sltp"] != (None, None)


class CloseDuringAmendAdapter(PaperAdapter):
    """The position's own stop fires while the amend is still in flight."""

    async def set_sltp(self, *, symbol, stop_loss, take_profit):
        self._position = None
        await asyncio.sleep(5.0)


async def test_an_amend_on_a_position_that_closed_is_superseded_not_failed():
    adapter = CloseDuringAmendAdapter(balance=D("1000"))
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
        timeout=0.5,
    )

    assert not result.failed
    assert not failure_notifications(result)
    assert result.succeeded[0].error_code == "position_closed"


# --- the re-read is not only for the deadline --------------------------------
#
# The per-request HTTP ceiling sits *below* the fan-out deadline
# (rest.default_timeout is 0.75 of the budget), so a slow venue usually raises
# ``ExchangeUnavailable: request timed out`` long before the leg is cancelled.
# Those legs were reported as plain failures and never re-read — which is how a
# position the exchange had already opened was shown to the admin as a failure.


class DroppedReplyAdapter(PaperAdapter):
    """The entry lands; the reply never comes back.

    The HTTP client's own read timeout, a reset connection, a 5xx from a proxy
    — every one of them raises inside the leg, well under the deadline.
    """

    async def place_order(self, **kwargs):
        await super().place_order(**kwargs)
        raise ExchangeUnavailable("paper: request timed out")


async def test_an_entry_that_failed_short_of_the_deadline_is_still_re_read():
    adapter = DroppedReplyAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], intent())

    assert not result.failed, "a position that exists is not a failure"
    assert not failure_notifications(result)
    leg = result.succeeded[0]
    assert leg.error_code == "late_fill"
    assert leg.value.qty == (await adapter.get_position("BTCUSDT")).size


async def test_an_entry_the_exchange_holds_nothing_for_is_recorded_as_not_filled():
    """The reason is kept; the code becomes the fact that it never landed."""
    result = await open_trade(
        [(1, PaperAdapter(balance=D("1000"), fail_on={"place_order"}))], intent()
    )

    leg = result.failed[0]
    assert leg.error_code == "not_filled"
    assert "no position was opened" in leg.error
    assert leg.error_code in SAT_OUT_CODES, "the account is free for the next trade"


class OppositePositionAdapter(PaperAdapter):
    """The account already holds a short, put there by something else."""

    async def place_order(self, **kwargs):
        raise ExchangeUnavailable("paper: request timed out")

    async def get_position(self, symbol):
        return Position(
            symbol=symbol,
            side=Side.SHORT,
            size=D("0.5"),
            entry_price=D("100000"),
            liquidation_price=None,
            unrealized_pnl=D("0"),
            leverage=10,
        )


async def test_a_position_on_the_other_side_is_never_claimed_as_this_legs_fill():
    """Someone else's position must not become this trade's size and entry."""
    result = await open_trade([(1, OppositePositionAdapter(balance=D("1000")))], intent())

    leg = result.failed[0]
    assert leg.error_code != "late_fill"
    assert leg.value is None


class CountingAdapter(PaperAdapter):
    """Counts the re-reads, so "we did not ask" can be asserted."""

    reads = 0

    async def get_position(self, symbol):
        type(self).reads += 1
        return await super().get_position(symbol)


async def test_a_leg_that_provably_never_sent_an_order_is_not_re_read():
    """Spec §5 sizing skips cost nothing: there is nothing to ask about."""
    CountingAdapter.reads = 0
    result = await open_trade([(1, CountingAdapter(balance=D("1")))], intent())

    assert result.failed[0].error_code == "below_min_qty"
    assert CountingAdapter.reads == 0


class UnreachableAdapter(PaperAdapter):
    """The venue is simply not answering — not the order, not the re-read."""

    async def place_order(self, **kwargs):
        raise ExchangeUnavailable("paper: request timed out")

    async def get_position(self, symbol):
        raise ExchangeUnavailable("paper: request timed out")


async def test_a_leg_the_exchange_will_not_answer_says_it_is_unknown():
    """The admin has to be told to go and look — not that nothing happened."""
    result = await open_trade([(1, UnreachableAdapter(balance=D("1000")))], intent())

    leg = result.failed[0]
    assert leg.error_code != "not_filled"
    assert "NOT known whether this order landed" in leg.error
    assert leg.error_code not in SAT_OUT_CODES, "still in scope for close"


async def test_an_unconfirmed_entry_is_settled_by_a_later_re_read():
    """``confirm_open``: the same question, asked once the response is gone."""
    adapter = DroppedReplyAdapter(balance=D("1000"))
    await open_trade([(1, adapter)], intent())

    result = await confirm_open([(1, adapter)], intent())

    leg = result.succeeded[0]
    assert leg.error_code == "late_fill"
    assert leg.value.entry_price == (await adapter.get_position("BTCUSDT")).entry_price
