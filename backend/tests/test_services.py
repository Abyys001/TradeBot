"""End-to-end routing: database -> adapters -> fan-out -> persistence.

Uses paper adapters so nothing touches a real exchange, but exercises the real
service layer, the real models, and the real notification path.
"""

from __future__ import annotations

import asyncio

import pytest
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange, Notification
from apps.core.money import D
from apps.exchanges.base import MarketType, OrderType, Side
from apps.exchanges.paper import PaperAdapter
from apps.trading.models import Trade, TradeLeg, TradeStatus
from apps.trading.services import (
    eligible_accounts,
    refresh_balances,
    route_amend,
    route_close,
    route_open,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

KEY = Fernet.generate_key().decode()


@sync_to_async
def make_account(label: str, *, balance: str = "1000", status=AccountStatus.ACTIVE):
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=status,
        withdrawal_check_passed=True,
        last_balance=D(balance),
        last_balance_asset="USDT",
    )


async def open_a_trade():
    return await route_open(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        limit_price=D("100000"),
    )


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_open_persists_a_leg_per_account():
    await make_account("partner-a", balance="1000")
    await make_account("partner-b", balance="5000")

    trade, result = await open_a_trade()

    assert result.all_ok
    legs = await sync_to_async(lambda: list(trade.legs.all()))()
    assert len(legs) == 2
    assert all(leg.ok for leg in legs)
    # Spec §5: same leverage, different dollar size.
    sizes = sorted(leg.margin for leg in legs)
    assert sizes == [D("990"), D("4950")]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_paused_accounts_are_excluded():
    """Spec §6: a paused account receives no new orders."""
    await make_account("active-one")
    await make_account("paused-one", status=AccountStatus.PAUSED)

    trade, result = await open_a_trade()

    assert len(result.legs) == 1
    legs = await sync_to_async(lambda: list(trade.legs.select_related("account")))()
    assert legs[0].account.label == "active-one"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_account_connected_after_the_trade_does_not_join_it():
    """Spec §6: no account joins a trade already in progress."""
    await make_account("early")
    trade, _ = await open_a_trade()

    late = await make_account("late")
    await sync_to_async(
        lambda: ConnectedAccount.objects.filter(pk=late.pk).update(
            eligible_from=timezone.now()
        )
    )()

    accounts = await eligible_accounts(trade)
    labels = {account.label for account in accounts}
    assert labels == {"early"}, "an account that connected mid-trade joined it"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_failing_account_is_recorded_and_notified_not_swallowed():
    """Spec §4: the other accounts still fill, and the failure is persistent."""
    await make_account("good", balance="1000")
    # 99% of 1 cent cannot meet any exchange minimum, so this leg fails.
    await make_account("too-small", balance="0.01")

    trade, result = await open_a_trade()

    assert len(result.succeeded) == 1
    assert len(result.failed) == 1

    legs = await sync_to_async(lambda: list(trade.legs.select_related("account")))()
    failed = [leg for leg in legs if not leg.ok]
    assert len(failed) == 1
    assert failed[0].account.label == "too-small"
    assert failed[0].error

    notifications = await sync_to_async(lambda: list(Notification.objects.all()))()
    assert len(notifications) == 1
    assert notifications[0].dismissed_at is None  # persists until dismissed


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_close_records_pnl_per_account():
    """Spec §8: each account keeps its own P/L for the trade."""
    await make_account("partner-a", balance="1000")
    await make_account("partner-b", balance="2000")

    trade, _ = await open_a_trade()
    result = await route_close(trade=trade)

    assert result.all_ok
    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.CLOSED
    assert refreshed.closed_at is not None

    legs = await sync_to_async(lambda: list(TradeLeg.objects.filter(trade=trade)))()
    assert all(leg.closed_at is not None for leg in legs)
    assert all(leg.pnl is not None for leg in legs)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_closing_does_not_overwrite_why_an_account_sat_out():
    """A leg that never entered always fails to close; that must not hide the
    original reason the account was skipped."""
    await make_account("good", balance="1000")
    await make_account("too-small", balance="0.01")

    trade, _ = await open_a_trade()
    original = await sync_to_async(
        lambda: TradeLeg.objects.get(trade=trade, account__label="too-small").error
    )()

    await route_close(trade=trade)

    after = await sync_to_async(
        lambda: TradeLeg.objects.get(trade=trade, account__label="too-small").error
    )()
    assert after == original
    assert "no open position" not in after


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_pausing_an_account_does_not_strand_its_open_position():
    """G4 / spec §6: pause stops *new* orders, it does not orphan a live one.

    Pausing only flipped the status, and every amend/close filtered on
    ACTIVE — so the position could never be closed or re-protected through the
    platform again, not even after a resume (which moves ``eligible_from``
    past the trade).
    """
    account = await make_account("partner-a")
    trade, result = await open_a_trade()
    assert result.all_ok

    await sync_to_async(
        lambda: ConnectedAccount.objects.filter(pk=account.pk).update(
            status=AccountStatus.PAUSED
        )
    )()

    amended = await route_amend(trade=trade, sl_pct=D("0.3"), tp_pct=D("2"))
    assert amended.all_ok, "a paused account's stop can no longer be moved"

    closed = await route_close(trade=trade)
    assert closed.all_ok, "a paused account's position cannot be flattened"

    leg = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()
    assert leg.closed_at is not None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_account_that_never_entered_is_not_asked_to_close():
    """G7: a leg that failed to enter has nothing to close or amend.

    It used to be fanned out on every subsequent action, fail with "no open
    position" each time, and mint a fresh persistent notification per action —
    burying the one notice that actually explained the skip.
    """
    await make_account("good", balance="1000")
    await make_account("too-small", balance="0.01")

    trade, _ = await open_a_trade()
    assert await sync_to_async(Notification.objects.count)() == 1

    await route_amend(trade=trade, sl_pct=D("0.3"), tp_pct=D("2"))
    await route_close(trade=trade)

    assert await sync_to_async(Notification.objects.count)() == 1, (
        "the failed entry was re-notified on every later action"
    )


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_account_connected_after_the_trade_still_cannot_join_an_amend():
    """Spec §6 again, now that eligibility for an open trade is leg-based."""
    await make_account("early")
    trade, _ = await open_a_trade()
    await make_account("late")

    accounts = await eligible_accounts(trade)

    assert {account.label for account in accounts} == {"early"}


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_fanout_duration_is_recorded_for_audit():
    """Spec §4 is a contract; recording the timing makes it checkable."""
    await make_account("a")
    await make_account("b")

    trade, result = await open_a_trade()

    assert trade.fanout_ms is not None
    assert result.within_budget()
    legs = await sync_to_async(lambda: list(trade.legs.all()))()
    assert all(leg.dispatch_ms is not None for leg in legs)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_balance_refresh_covers_paused_accounts():
    """Spec §6 says *every* connected account, and a paused one is exactly the
    account whose balance you check before deciding to resume it."""
    await make_account("live-one")
    await make_account("paused-one", status=AccountStatus.PAUSED)

    rows = await refresh_balances(force=True)

    assert {row["label"] for row in rows} == {"live-one", "paused-one"}


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_background_refresh_is_rate_limited_but_still_answers():
    """Five open panels must not mean five fan-outs to every exchange."""
    account = await make_account("partner-a")

    first = await refresh_balances()
    second = await refresh_balances()

    assert [row["label"] for row in first] == ["partner-a"]
    # The second caller is inside the window: same account, no exchange call.
    assert [row["label"] for row in second] == ["partner-a"]
    assert second[0]["id"] == account.id

    # A human pressing refresh is never rate-limited.
    forced = await refresh_balances(force=True)
    assert [row["label"] for row in forced] == ["partner-a"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_market_order_needs_no_limit_price():
    """A market order carries no price, but sizing does — qty is notional/price.

    The paper adapter prices itself, so demo mode works with no feed at all.
    """
    await make_account("partner-a", balance="1000")

    trade, result = await route_open(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=5,
        sl_pct=D("1"),
        tp_pct=D("2"),
        limit_price=None,
    )

    assert result.all_ok, [leg.error for leg in result.failed]
    leg = (await sync_to_async(lambda: list(trade.legs.all()))())[0]
    assert leg.qty and leg.entry_price


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_synthetic_price_never_sizes_a_trade():
    """Market data falls back to synthetic when offline; sizing must not use it."""
    from apps.trading.services import _reference_price

    assert await _reference_price("BTCUSDT", MarketType.FUTURES) is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_no_eligible_accounts_records_no_trade():
    """Zero connected accounts must not raise, and must not leave a ghost trade.

    An empty trade row would sit in the history and in the positions panel
    forever, looking like a position that nobody actually holds.
    """
    trade, result = await open_a_trade()
    assert result.legs == []
    assert trade is None
    assert await sync_to_async(Trade.objects.count)() == 0


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_account_already_in_a_trade_sits_the_next_one_out():
    """Spec §5: one open trade per account — 99% of the balance is committed."""
    await make_account("partner-a")
    await make_account("partner-b")

    first, _ = await open_a_trade()
    assert first is not None

    # partner-a stays in; only partner-b is free to take a second entry. Close
    # partner-a's leg by hand so the two accounts differ.
    await sync_to_async(
        lambda: first.legs.filter(account__label="partner-b").update(
            closed_at=timezone.now(), ok=False
        )
    )()

    second, result = await open_a_trade()
    assert second is not None
    labels = await sync_to_async(lambda: [leg.account.label for leg in second.legs.all()])()
    assert labels == ["partner-b"], "an account already holding a position must sit out"


class SlowReplyAdapter(PaperAdapter):
    """The entry lands on the exchange but the reply never reaches us in time."""

    async def place_order(self, **kwargs):
        await super().place_order(**kwargs)
        await asyncio.sleep(5.0)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_late_fill_persists_as_ok_with_no_failure_notification(monkeypatch):
    """Q19: a timed-out leg that actually filled is ok in the DB, not a failure."""
    account = await make_account("slow-venue", balance="1000")

    def fake_adapters(accounts):
        return [(account.pk, SlowReplyAdapter(balance=D("1000")))]

    monkeypatch.setattr("apps.trading.services._adapters", fake_adapters)

    trade, result = await open_a_trade()

    assert result.all_ok
    assert result.succeeded[0].error_code == "late_fill"
    leg = await sync_to_async(lambda: trade.legs.get())()
    assert leg.ok
    assert leg.error_code == "late_fill"
    assert "confirmed on the exchange" in leg.error
    assert await sync_to_async(Notification.objects.count)() == 0
