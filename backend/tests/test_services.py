"""End-to-end routing: database -> adapters -> fan-out -> persistence.

Uses paper adapters so nothing touches a real exchange, but exercises the real
service layer, the real models, and the real notification path.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest import mock

import pytest
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange, Notification
from apps.core.money import D
from apps.exchanges import pool
from apps.exchanges.base import AdapterError, MarketType, OrderType, Side
from apps.exchanges.paper import PaperAdapter
from apps.trading.models import Trade, TradeLeg, TradeReduction, TradeStatus
from apps.trading.services import (
    NoLegsToRoute,
    eligible_accounts,
    reconcile_open_trade,
    refresh_balances,
    route_amend,
    route_close,
    route_close_all,
    route_open,
    route_reduce,
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


async def _assign(label: str, bot) -> ConnectedAccount:
    account = await ConnectedAccount.objects.aget(label=label)
    account.bot = bot
    await sync_to_async(account.save)(update_fields=["bot"])
    return account


async def _a_bot(name: str = "bot"):
    from tests.bot_factory import make_bot

    return await sync_to_async(make_bot)(name=name)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_manual_entry_skips_an_account_a_bot_drives():
    """Q42: an account answers to one hand. A manual entry landing on a bot's
    book would leave that bot describing a position it no longer has."""
    bot = await _a_bot()
    await make_account("bot-driven")
    await _assign("bot-driven", bot)
    await make_account("manual")

    accounts = await eligible_accounts(source="manual")

    assert [a.label for a in accounts] == ["manual"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bot_entry_only_reaches_the_accounts_assigned_to_that_bot():
    """None by default — a bot fanning out to an account nobody handed it is
    the one mistake the assignment exists to prevent — and never another
    bot's, which is what lets several run at once."""
    mine, theirs = await _a_bot("mine"), await _a_bot("theirs")
    await make_account("manual")
    await make_account("mine")
    await make_account("theirs")
    await _assign("mine", mine)
    await _assign("theirs", theirs)

    accounts = await eligible_accounts(source="bot", bot_id=mine.id)

    assert [a.label for a in accounts] == ["mine"]


async def test_a_bot_entry_that_does_not_name_its_bot_is_refused():
    with pytest.raises(ValueError):
        await eligible_accounts(source="bot")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_route_open_for_a_bot_only_fans_out_to_its_own_accounts():
    bot = await _a_bot()
    await make_account("bot-on", balance="1000")
    await make_account("manual", balance="1000")
    await _assign("bot-on", bot)

    trade, result = await route_open(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        limit_price=D("100000"),
        source="bot",
        bot_id=bot.id,
    )

    legs = await sync_to_async(lambda: list(trade.legs.select_related("account")))()
    assert [leg.account.label for leg in legs] == ["bot-on"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bot_entry_commits_ninety_nine_percent_of_every_account_it_reaches():
    """Spec §5 is not a manual-only rule.

    A bot is a signal source, not a second execution path, so its entry goes
    through the same ``route_open`` and the same ``size_order``. Checked
    end-to-end rather than trusted: this is the number that decides how much of
    a partner's capital a strategy commits.
    """
    bot = await _a_bot()
    for label, balance in (("small", "10"), ("medium", "50"), ("large", "100")):
        await make_account(label, balance=balance)
        await _assign(label, bot)

    trade, _ = await route_open(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        source="bot",
        bot_id=bot.id,
    )

    legs = await sync_to_async(lambda: list(trade.legs.select_related("account")))()
    margins = {leg.account.label: leg.margin for leg in legs if leg.ok}
    # 99% of each balance, rounded down to the exchange step — never up, and
    # never a share of some pooled total.
    assert margins["medium"] == D("49.50")
    assert margins["large"] == D("99.00")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_paused_account_never_takes_a_bot_entry_however_it_is_assigned():
    """Two independent conditions, and both have to hold.

    An assignment on a paused account is an intention, not a permission — the
    commonest way a fan-out would reach somewhere it should not is one of the
    two being checked and the other assumed.
    """
    bot = await _a_bot()
    await make_account("paused", status=AccountStatus.PAUSED)
    await _assign("paused", bot)
    await make_account("active-assigned")
    await _assign("active-assigned", bot)

    accounts = await eligible_accounts(source="bot", bot_id=bot.id)
    assert [a.label for a in accounts] == ["active-assigned"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bot_trade_is_in_the_ledger_arithmetic_like_any_other():
    """The money side does not know a bot placed it, and must not.

    ``detection`` subtracts the legs the platform closed itself from what equity
    did; a trade that was invisible to it would be booked as an unexplained
    transfer, which is a wrong PnL in both directions.
    """
    from apps.accounts.detection import _closed_trade_pnl

    bot = await _a_bot()
    await make_account("ledger", balance="1000")
    account = await _assign("ledger", bot)

    trade, _ = await route_open(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        source="bot",
        bot_id=bot.id,
    )
    await route_close(trade=trade)

    @sync_to_async
    def booked() -> D:
        leg = TradeLeg.objects.filter(trade=trade).first()
        leg.pnl = D("12.34")
        leg.closed_at = timezone.now()
        leg.save(update_fields=["pnl", "closed_at"])
        return _closed_trade_pnl(
            account, timezone.now() - timedelta(hours=1), timezone.now()
        )

    assert await booked() == D("12.34")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_manual_and_bot_books_are_disjoint_and_trade_at_the_same_time():
    """Q42: the admin's ticket and a running bot each reach only their own
    accounts, so both can hold a position at once without touching the other's."""
    bot = await _a_bot()
    await make_account("manual", balance="1000")
    await make_account("botted", balance="1000")
    await _assign("botted", bot)

    common = dict(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        limit_price=D("100000"),
    )
    bot_trade, _ = await route_open(**common, source="bot", bot_id=bot.id)
    manual_trade, _ = await route_open(**common)

    labels = lambda t: sync_to_async(  # noqa: E731
        lambda: [leg.account.label for leg in t.legs.select_related("account")]
    )()
    assert await labels(bot_trade) == ["botted"]
    assert await labels(manual_trade) == ["manual"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_closing_one_account_leaves_the_rest_of_the_trade_open():
    """Q42's reassignment closes one account's leg; the trade runs on."""
    await make_account("leaving", balance="1000")
    await make_account("staying", balance="1000")
    trade, _ = await open_a_trade()
    leaving = await ConnectedAccount.objects.aget(label="leaving")

    await route_close(trade=trade, account_ids=[leaving.id])

    await trade.arefresh_from_db()
    assert trade.status == TradeStatus.OPEN
    legs = await sync_to_async(
        lambda: {leg.account.label: leg.closed_at for leg in trade.legs.select_related("account")}
    )()
    assert legs["leaving"] is not None
    assert legs["staying"] is None

    await route_close(trade=trade)
    await trade.arefresh_from_db()
    assert trade.status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_bot_dispatched_trade_is_stamped_and_labelled_on_the_wire():
    """The chart draws a bot's own entries/exits through the exact same marker
    mechanism as a manual trade (bots.md §7) — it only needs the bot's name,
    which ``TradeSerializer.bot_name`` carries from ``Trade.bot_run``."""
    from apps.bots import translate
    from apps.pine.intent import Side as PineSide
    from apps.trading.serializers import TradeSerializer
    from tests.bot_factory import make_bot, make_run

    bot = await sync_to_async(make_bot)(name="my strategy")
    await make_account("bot-on", balance="1000")
    await _assign("bot-on", bot)
    run = await sync_to_async(make_run)(bot)

    action = translate.Action(type="open", side=PineSide.LONG, sl_pct=D("1"), tp_pct=D("2"))
    outcomes = await translate.dispatch(bot=bot, run=run, bar_time=1, actions=[action])

    assert outcomes[0]["ok"] is True
    trade = await Trade.objects.aget(id=outcomes[0]["trade_id"])
    assert trade.bot_run_id == run.id
    data = await sync_to_async(lambda: TradeSerializer(trade).data)()
    assert data["bot_run"] == run.id
    assert data["bot_name"] == "my strategy"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_manual_trades_bot_name_is_null_on_the_wire():
    from apps.trading.serializers import TradeSerializer

    await make_account("partner-a")
    trade, _ = await open_a_trade()

    data = await sync_to_async(lambda: TradeSerializer(trade).data)()

    assert data["bot_run"] is None
    assert data["bot_name"] is None


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
async def test_an_amend_persists_the_verified_resting_prices_per_leg():
    """The DB stores what the exchange holds, read back after the amend.

    This pins the fix for the chart showing the open-time stop after an amend:
    ``_save_amend`` used to write only the trade's percentages, never the
    per-leg prices, so ``/positions/`` kept re-deriving open-time values.
    """
    await make_account("partner-a")
    trade, _ = await open_a_trade()

    amended = await route_amend(trade=trade, sl_pct=D("0.5"), tp_pct=D("1"))
    assert amended.all_ok

    leg = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()
    assert leg.sltp_verified is True
    assert leg.sltp_attached is True
    assert leg.stop_loss is not None
    assert leg.take_profit is not None
    # The stop sits on the loss side of the fill and the target on the win side
    # — the prices the exchange actually holds, not percentages re-derived here.
    assert leg.stop_loss < leg.entry_price < leg.take_profit


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_failed_amend_keeps_the_old_resting_prices_on_the_leg():
    """An account still on its old stop must never be recorded at the new price."""
    await make_account("partner-a")
    trade, _ = await open_a_trade()
    before = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()

    with mock.patch.object(
        PaperAdapter, "set_sltp", side_effect=AdapterError("exchange unreachable")
    ):
        amended = await route_amend(trade=trade, sl_pct=D("0.9"), tp_pct=D("9"))
    assert not amended.all_ok

    after = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()
    assert after.stop_loss == before.stop_loss
    assert after.take_profit == before.take_profit
    assert after.sltp_attached is True
    assert after.sltp_verified is True


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


# --- a live position must stay reachable (the "close did nothing" report) ----


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_leg_that_filled_but_failed_protection_can_still_be_closed():
    """The bug behind "close says closed, the exchange still holds it".

    An entry that fills and then fails to attach SL/TP is recorded ``ok=False``
    while the exchange holds a live position — the engine says so itself
    ("the position is open and may be UNPROTECTED"). Eligibility used to key on
    ``ok``, so that leg vanished from every later amend and close: the fan-out
    ran with zero legs, finished in microseconds, reported success, and the
    trade was stamped CLOSED over a position nobody had closed.
    """
    await make_account("partner-a")
    trade, _ = await open_a_trade()

    # Exactly the shape _reconcile_open persists for a late fill it could not
    # protect: failed leg, still open, position live on the exchange.
    await sync_to_async(
        lambda: trade.legs.update(
            ok=False,
            error="entry filled after the deadline but the SL/TP attach was cut off",
            error_code="sltp_unconfirmed",
        )
    )()

    accounts = await eligible_accounts(trade)
    assert [a.label for a in accounts] == ["partner-a"], (
        "a leg holding a live position was excluded from the close"
    )

    result = await route_close(trade=trade)
    assert result.all_ok, [leg.error for leg in result.failed]

    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_leg_that_never_placed_an_order_still_sits_out():
    """The other half: a sizing skip holds nothing, so it is not asked to close."""
    await make_account("good", balance="1000")
    await make_account("too-small", balance="0.01")

    trade, result = await open_a_trade()
    assert len(result.failed) == 1

    accounts = await eligible_accounts(trade)
    assert [a.label for a in accounts] == ["good"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_close_with_an_unreachable_leg_refuses_instead_of_reporting_success():
    """Zero *reachable* legs is never a close. The trade must stay OPEN."""
    await make_account("partner-a")
    trade, _ = await open_a_trade()

    # The leg filled, so the exchange may be holding it — and no adapter can be
    # built to ask (credentials replaced, exchange unreachable, key rotated).
    with mock.patch.object(pool, "get", side_effect=RuntimeError("cannot build")):
        with pytest.raises(NoLegsToRoute):
            await route_close(trade=trade)

    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.OPEN, "an unrouted close closed the trade"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_close_with_nothing_left_to_hold_retires_the_trade():
    """The other side of it: nothing to route *because* nothing is held.

    Refusing here was a deadlock with no way out of the panel — the trade
    blocked the next order ("a trade is already open") and close answered "no
    account could be reached" forever, over a position no exchange held.
    """
    await make_account("partner-a")
    trade, _ = await open_a_trade()

    # Every leg proven to have sat the entry out, and no adapter can be built
    # to ask anyway -> nothing to send, and nothing that could be held.
    await sync_to_async(lambda: trade.legs.update(ok=False, error_code="below_min_notional"))()

    with mock.patch.object(pool, "get", side_effect=RuntimeError("cannot build")):
        result = await route_close(trade=trade)

    assert result.legs == []
    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_trade_whose_legs_were_all_closed_one_by_one_does_not_stay_open():
    """A filled leg that is already closed counts as flat.

    Judging the trade on "did any leg fill?" alone kept it OPEN after its last
    position had been flattened, and every account was then out of scope for
    close — the ticket stayed blocked with nothing left to send.
    """
    await make_account("partner-a", balance="1000")
    await make_account("too-small", balance="0.01")
    trade, result = await open_a_trade()
    assert len(result.failed) == 1

    await sync_to_async(
        lambda: trade.legs.filter(ok=True).update(closed_at=timezone.now())
    )()

    assert await reconcile_open_trade(), "the poll left a trade nobody holds open"
    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_leg_the_exchange_would_not_flatten_keeps_the_trade_open():
    """A close that fails on the exchange must not stamp the trade CLOSED."""
    await make_account("partner-a")
    trade, _ = await open_a_trade()

    async def refuse(self, symbol):
        raise AdapterError("exchange rejected the close")

    with mock.patch.object(PaperAdapter, "close_position", refuse):
        result = await route_close(trade=trade)

    assert not result.all_ok
    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.OPEN

    leg = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()
    assert leg.closed_at is None, "a leg still on the exchange was marked closed"


# --- the fill that arrives after the response is gone -------------------------


class NoReplyAdapter(PaperAdapter):
    """The entry lands; the reply never comes back at all."""

    async def place_order(self, **kwargs):
        await super().place_order(**kwargs)
        raise AdapterError("paper: request timed out")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_unconfirmed_leg_becomes_a_real_position_on_the_next_poll(monkeypatch):
    """The panel's picture has to end up matching the exchange's.

    The re-read inside ``route_open`` is bounded by the admin's request. This
    is the same account asked again once that response is long gone, which is
    the only way a fill nobody could confirm in time turns into a position the
    positions panel counts.
    """
    account = await make_account("slow-venue", balance="1000")
    adapter = NoReplyAdapter(balance=D("1000"))

    def fake_adapters(accounts):
        return [(account.pk, adapter)]

    monkeypatch.setattr("apps.trading.services._adapters", fake_adapters)
    # The bounded re-read cannot answer either: the venue is still silent.
    monkeypatch.setattr(adapter, "get_position", mock.AsyncMock(side_effect=TimeoutError))
    trade, result = await open_a_trade()

    leg = await sync_to_async(lambda: trade.legs.get())()
    assert not leg.ok
    assert "NOT known whether this order landed" in leg.error

    # The venue comes back. Nothing was re-sent; it is only asked again.
    monkeypatch.delattr(adapter, "get_position")
    cache.delete("trading:unconfirmed:checked_at")
    assert await reconcile_open_trade() is True

    leg = await sync_to_async(lambda: trade.legs.get())()
    assert leg.ok
    assert leg.error_code == "late_fill"
    assert leg.qty == (await adapter.get_position("BTCUSDT")).size
    assert leg.entry_price is not None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_unconfirmed_account_cannot_be_given_a_second_position(monkeypatch):
    """Spec §5 is one open trade per account, and "unknown" is not "none"."""
    account = await make_account("slow-venue", balance="1000")

    def fake_adapters(accounts):
        return [(account.pk, PaperAdapter(balance=D("1000"), fail_on={"get_position"}))]

    monkeypatch.setattr("apps.trading.services._adapters", fake_adapters)
    await open_a_trade()

    assert await eligible_accounts() == []


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_account_the_exchange_says_is_flat_trades_again(monkeypatch):
    """The block above must not be permanent: ``not_filled`` frees the account."""
    account = await make_account("rejected", balance="1000")

    def fake_adapters(accounts):
        return [(account.pk, PaperAdapter(balance=D("1000"), fail_on={"place_order"}))]

    monkeypatch.setattr("apps.trading.services._adapters", fake_adapters)
    trade, _ = await open_a_trade()

    leg = await sync_to_async(lambda: trade.legs.get())()
    assert leg.error_code == "not_filled"
    assert [a.pk for a in await eligible_accounts()] == [account.pk]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_fanout_that_filled_nothing_leaves_no_open_trade(monkeypatch):
    """An entry nobody took must not block the next one.

    Every leg here sat the entry out, so no exchange holds anything — and the
    accounts are freed accordingly. The trade row has to agree: while it stayed
    OPEN, ``/positions/`` reported a position nobody held, the ticket refused
    the next order with "a trade is already open", and close could not clear it
    either because the same trade resolves to zero legs to send.
    """
    account = await make_account("rejected", balance="1000")

    def fake_adapters(accounts):
        return [(account.pk, PaperAdapter(balance=D("1000"), fail_on={"place_order"}))]

    monkeypatch.setattr("apps.trading.services._adapters", fake_adapters)
    trade, _ = await open_a_trade()

    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.CLOSED
    assert refreshed.closed_at is not None
    # The failure is still in the history, and still in the panel's face.
    leg = await sync_to_async(lambda: refreshed.legs.get())()
    assert leg.error_code == "not_filled"
    assert await sync_to_async(Notification.objects.count)() == 1
    assert not await sync_to_async(Trade.objects.filter(status=TradeStatus.OPEN).exists)()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_late_reconcile_that_finds_nothing_closes_the_trade(monkeypatch):
    """The same rule when the answer arrives after the response is gone."""
    account = await make_account("slow-venue", balance="1000")
    adapter = PaperAdapter(balance=D("1000"), fail_on={"place_order"})

    def fake_adapters(accounts):
        return [(account.pk, adapter)]

    monkeypatch.setattr("apps.trading.services._adapters", fake_adapters)
    # The bounded re-read cannot answer, so the leg is unconfirmed: the trade
    # stays open, because an account that may hold a position is not free.
    monkeypatch.setattr(adapter, "get_position", mock.AsyncMock(side_effect=TimeoutError))
    trade, _ = await open_a_trade()
    assert (await sync_to_async(Trade.objects.get)(pk=trade.pk)).status == TradeStatus.OPEN

    monkeypatch.delattr(adapter, "get_position")
    cache.delete("trading:unconfirmed:checked_at")
    assert await reconcile_open_trade() is True

    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.CLOSED
    assert [a.pk for a in await eligible_accounts()] == [account.pk]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_close_all_closes_every_open_trade_not_just_the_newest():
    """Two trades can be open at once, and the close button must clear both.

    An account freed by a close can take the next entry while the others are
    still in the old trade, so the platform holds two OPEN rows. Closing only
    the one the panel happens to show left the other live on the exchange with
    the panel reporting flat.
    """
    await make_account("partner-a", balance="1000")
    first, _ = await open_a_trade()

    # A second account connects afterwards; spec §6 keeps it out of the trade
    # in progress, so its entry opens a trade of its own.
    await make_account("partner-b", balance="2000")
    second, _ = await open_a_trade()
    assert first is not None and second is not None and first.id != second.id

    closed = await route_close_all()

    assert {trade.id for trade, _ in closed} == {first.id, second.id}
    assert all(result.all_ok for _, result in closed), [
        leg.error for _, result in closed for leg in result.failed
    ]
    for trade in (first, second):
        refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
        assert refreshed.status == TradeStatus.CLOSED
    open_legs = await sync_to_async(
        TradeLeg.objects.filter(closed_at__isnull=True).count
    )()
    assert open_legs == 0


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_close_all_with_nothing_open_is_not_an_error():
    """The button must be safe to press twice; the second press has no trades."""
    await make_account("partner-a", balance="1000")
    await open_a_trade()
    await route_close_all()

    assert await route_close_all() == []


# --- the scale-out (Q33) ----------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_scale_out_banks_the_slice_and_leaves_the_trade_open():
    await make_account("partner-a", balance="1000")
    await make_account("partner-b", balance="2000")

    trade, _ = await open_a_trade()
    result = await route_reduce(trade=trade, fraction=D("0.6"))

    assert result.all_ok
    refreshed = await sync_to_async(Trade.objects.get)(pk=trade.pk)
    assert refreshed.status == TradeStatus.OPEN
    assert refreshed.open_fraction == D("0.6")

    legs = await sync_to_async(lambda: list(TradeLeg.objects.filter(trade=trade)))()
    for leg in legs:
        assert leg.closed_at is None, "a partial exit is not a close"
        assert leg.qty < leg.entry_qty
        assert leg.realized_pnl is not None

    rows = await sync_to_async(lambda: list(TradeReduction.objects.filter(leg__trade=trade)))()
    assert len(rows) == len(legs)
    assert all(row.to_fraction == D("0.6") for row in rows)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_final_close_prices_only_what_is_left():
    """`_persist_close` computes from `leg.qty`, which by then is the
    remainder — so the account's realised total is the close plus what the
    levels banked, and neither half is counted twice."""
    await make_account("partner-a", balance="1000")

    trade, _ = await open_a_trade()
    await route_reduce(trade=trade, fraction=D("0.5"))
    leg = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()
    remaining, banked = leg.qty, leg.realized_pnl

    await route_close(trade=trade)
    leg = await sync_to_async(lambda: TradeLeg.objects.get(trade=trade))()
    assert leg.qty == remaining
    assert leg.realized_pnl == banked
    assert leg.closed_at is not None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_scale_out_reaches_a_leg_whose_protection_failed():
    """The same asymmetry close relies on: a leg recorded ok=False may still be
    a live position at leverage, and it must not be left out of the exit."""
    await make_account("unprotected", balance="1000")
    trade, _ = await open_a_trade()
    await sync_to_async(TradeLeg.objects.filter(trade=trade).update)(
        ok=False, error_code="sltp_failed"
    )
    accounts = await eligible_accounts(trade)
    assert len(accounts) == 1
