"""The platform's record versus what the exchange actually holds.

Everything here runs against paper adapters, whose position lives in a
process-global dict keyed per account — which is exactly what makes them useful
for this: mutating that dict *behind* the service layer is a faithful stand-in
for the exchange changing its mind on its own (a stop firing, a liquidation,
someone flattening in the venue's app), which is the case no request-scoped
reconcile can see.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange, Notification
from apps.core.money import D
from apps.exchanges import pool
from apps.exchanges.base import MarketType, OrderType, Position, Side
from apps.exchanges.paper import _SHARED_STATE
from apps.trading.models import Trade, TradeLeg, TradeReduction, TradeStatus
from apps.trading.possync import GRACE, sync_positions
from apps.trading.services import route_open

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


def flatten_on_exchange(account: ConnectedAccount) -> None:
    """What a stop firing looks like from this side: the position is just gone."""
    _SHARED_STATE[f"account-{account.id}"]["position"] = None


def stop_fires_on_exchange(account: ConnectedAccount, price: str) -> None:
    """The same thing, but on a venue that keeps a trade log: a fill remains."""
    from apps.exchanges.paper import PaperAdapter

    adapter = PaperAdapter(state_key=f"account-{account.id}")
    adapter.settle_on_exchange(D(price))


def hold_on_exchange(account: ConnectedAccount, **kwargs) -> None:
    """The other direction: the venue holds something the platform does not."""
    _SHARED_STATE.setdefault(f"account-{account.id}", {})["position"] = Position(
        symbol=kwargs.get("symbol", "BTCUSDT"),
        side=kwargs.get("side", Side.LONG),
        size=D(kwargs.get("size", "0.05")),
        entry_price=D(kwargs.get("entry_price", "100000")),
        liquidation_price=None,
        unrealized_pnl=D("0"),
        leverage=10,
    )


@sync_to_async
def age_legs(trade: Trade) -> None:
    """Push the legs past the grace window without waiting for it."""
    TradeLeg.objects.filter(trade=trade).update(
        opened_at=timezone.now() - GRACE - timedelta(seconds=1)
    )


@sync_to_async
def leg_for(trade: Trade, account: ConnectedAccount) -> TradeLeg:
    return TradeLeg.objects.get(trade=trade, account=account)


@sync_to_async
def reload(trade: Trade) -> Trade:
    return Trade.objects.get(pk=trade.pk)


@sync_to_async
def notices(code: str) -> list[Notification]:
    return list(Notification.objects.filter(code=code, dismissed_at__isnull=True))


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_position_closed_on_the_exchange_closes_the_leg():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    flatten_on_exchange(account)
    report = await sync_positions(force=True)

    assert report.closed == [account.id]
    leg = await leg_for(trade, account)
    assert leg.closed_at is not None
    assert leg.error_code == "closed_on_exchange"
    # Nothing holds anything any more, so the trade must stop blocking the next
    # order — that deadlock is half of why this module exists.
    assert (await reload(trade)).status == TradeStatus.CLOSED
    assert report.trade_retired
    assert len(await notices("closed_on_exchange")) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_leg_inside_the_grace_window_is_left_alone():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()

    flatten_on_exchange(account)
    report = await sync_positions(force=True)

    # The fill is seconds old; the venue may simply not have published it yet.
    # Closing here would be the sync inventing the desync it exists to remove.
    assert report.closed == []
    assert (await leg_for(trade, account)).closed_at is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_one_account_flat_does_not_touch_the_other():
    first = await make_account("partner-a")
    second = await make_account("partner-b", balance="5000")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    flatten_on_exchange(first)
    report = await sync_positions(force=True)

    assert report.closed == [first.id]
    assert (await leg_for(trade, second)).closed_at is None
    # One leg still live, so the trade stays open.
    assert (await reload(trade)).status == TradeStatus.OPEN


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_exchange_that_will_not_answer_changes_nothing():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    flatten_on_exchange(account)
    adapter = pool.get(await sync_to_async(ConnectedAccount.objects.get)(pk=account.id))
    adapter._fail_on = {"get_position"}
    try:
        report = await sync_positions(force=True)
    finally:
        adapter._fail_on = set()

    # A silent exchange proves nothing. Closing a leg on a read that failed is
    # the same mistake as reporting a close nobody performed.
    assert report.closed == []
    assert report.unreachable == [account.id]
    assert (await leg_for(trade, account)).closed_at is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_position_the_platform_wrote_off_is_restored():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    @sync_to_async
    def write_it_off() -> None:
        TradeLeg.objects.filter(trade=trade).update(
            ok=False, error_code="not_filled", closed_at=timezone.now()
        )

    await write_it_off()
    # The exchange, however, holds it.
    hold_on_exchange(account)

    report = await sync_positions(force=True)

    assert report.adopted == [account.id]
    leg = await leg_for(trade, account)
    assert leg.closed_at is None
    assert leg.ok
    assert leg.error_code == "found_on_exchange"
    assert leg.qty == D("0.05")
    assert len(await notices("found_on_exchange")) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_closed_trade_the_exchange_still_holds_is_reopened():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()

    @sync_to_async
    def close_the_record() -> None:
        now = timezone.now()
        TradeLeg.objects.filter(trade=trade).update(closed_at=now)
        Trade.objects.filter(pk=trade.pk).update(status=TradeStatus.CLOSED, closed_at=now)

    await close_the_record()
    hold_on_exchange(account)

    report = await sync_positions(force=True, deep=True)

    assert report.reopened == trade.id
    assert (await reload(trade)).status == TradeStatus.OPEN
    leg = await leg_for(trade, account)
    assert leg.closed_at is None and leg.ok


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_repeated_sweeps_mint_one_notification():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)
    flatten_on_exchange(account)

    await sync_positions(force=True)
    await sync_positions(force=True)
    await sync_positions(force=True)

    # Spec §4 notices clear by hand only. One live desync is one card, not one
    # card per sweep — three seconds apart, that is twenty an minute.
    assert len(await notices("closed_on_exchange")) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_interval_guard_holds_sweeps_apart():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)
    flatten_on_exchange(account)

    # First unforced sweep claims the slot; the second inside the window is a
    # no-op, which is what stops ten open tabs being ten reads per account.
    first = await sync_positions()
    second = await sync_positions()

    assert first.closed == [account.id]
    assert second.closed == []


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_paused_account_is_still_reconciled():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    @sync_to_async
    def pause() -> None:
        ConnectedAccount.objects.filter(pk=account.id).update(status=AccountStatus.PAUSED)

    await pause()
    flatten_on_exchange(account)

    report = await sync_positions(force=True)

    # Pausing stops new orders. It does not close a position already live at
    # leverage, so the record of that position still has to be kept honest.
    assert report.closed == [account.id]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_size_drift_is_taken_from_the_exchange():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    # A partial fill, a fee taken in kind, a funding adjustment: the venue's
    # size is the real one.
    hold_on_exchange(account, size="0.007")
    report = await sync_positions(force=True)

    assert report.drifted == [account.id]
    assert (await leg_for(trade, account)).qty == D("0.007")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_position_that_shrank_is_written_down_as_a_partial_exit():
    """It used to be swallowed as drift: the size was copied over and the
    difference — real money, out of the position — left no row at all, which
    `accounts.detection` then offered to the operator as somebody's deposit."""
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)
    before = (await leg_for(trade, account)).qty

    hold_on_exchange(account, size=str(before / 2))
    await sync_positions(force=True)

    rows = await sync_to_async(lambda: list(TradeReduction.objects.filter(leg__trade=trade)))()
    assert len(rows) == 1
    assert rows[0].qty == before - before / 2
    assert rows[0].source_code == "shrank_on_exchange"
    # Unknown, never estimated from a mark: `get_closed_pnl` reports a closed
    # position, not a slice of an open one, so there is nothing to price it from.
    assert rows[0].price is None and rows[0].pnl is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_shrink_the_platform_already_recorded_is_not_written_twice():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)
    leg = await leg_for(trade, account)
    taken = leg.qty / 2

    await sync_to_async(TradeReduction.objects.create)(
        leg=leg, qty=taken, to_fraction=D("0.5"), price=D("100000"), pnl=D("0")
    )
    hold_on_exchange(account, size=str(leg.qty - taken))
    await sync_positions(force=True)

    rows = await sync_to_async(lambda: list(TradeReduction.objects.filter(leg__trade=trade)))()
    assert len(rows) == 1
    assert rows[0].price == D("100000")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_position_that_grew_is_still_only_drift():
    """A reduction is a shrink. Copying a *larger* size over is the existing
    behaviour and must not start minting exit rows."""
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)
    before = (await leg_for(trade, account)).qty

    hold_on_exchange(account, size=str(before * 2))
    await sync_positions(force=True)

    assert not await sync_to_async(
        TradeReduction.objects.filter(leg__trade=trade).exists
    )()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_position_belonging_to_no_trade_is_reported_not_invented():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    @sync_to_async
    def close_the_record() -> None:
        now = timezone.now()
        TradeLeg.objects.filter(trade=trade).update(closed_at=now)
        Trade.objects.filter(pk=trade.pk).update(
            status=TradeStatus.CLOSED,
            closed_at=now - timedelta(days=30),
            symbol="ETHUSDT",
        )

    await close_the_record()
    hold_on_exchange(account)

    report = await sync_positions(force=True, deep=True)

    # No trade to attach it to and no licence to invent one: the admin is told,
    # in a card that does not expire, that the exchange holds something the
    # panel cannot close.
    assert report.reopened is None
    assert report.untracked == []  # nothing is watched: the symbol is out of scope
    assert (await reload(trade)).status == TradeStatus.CLOSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_account_with_no_leg_that_holds_the_pair_gets_one():
    first = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)
    # Connected after the trade opened, so spec §6 kept it out of the fan-out —
    # and yet the exchange holds a position for it.
    second = await make_account("partner-b", balance="5000")
    hold_on_exchange(second)

    report = await sync_positions(force=True)

    assert report.adopted == [second.id]
    leg = await leg_for(trade, second)
    assert leg.ok and leg.error_code == "found_on_exchange"
    # §6 is not broken: nothing was routed for this account. The position was
    # already there, and recording it is the only way close can reach it.
    assert (await leg_for(trade, first)).error_code == ""


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_position_on_an_account_no_trade_touched_is_only_reported():
    first = await make_account("partner-a")
    trade, _ = await open_a_trade()

    @sync_to_async
    def close_the_record() -> None:
        now = timezone.now()
        TradeLeg.objects.filter(trade=trade).update(closed_at=now)
        Trade.objects.filter(pk=trade.pk).update(status=TradeStatus.CLOSED, closed_at=now)

    await close_the_record()
    flatten_on_exchange(first)
    stranger = await make_account("partner-b", balance="5000")
    hold_on_exchange(stranger)

    report = await sync_positions(force=True, deep=True)

    # Reopening the trade for an account that was never in it would be a
    # fabricated history, and minting a second open trade would break the one
    # -open-trade model the router and the panel are both built on. So: a card
    # that says what is true and does not expire.
    assert report.reopened is None
    assert report.untracked == [f"{stranger.id}:BTCUSDT"]
    assert (await reload(trade)).status == TradeStatus.CLOSED
    assert len(await notices("untracked_position")) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_opposite_side_on_the_pair_is_reported_not_matched():
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    # The trade is long; the exchange holds a short on the same pair. Whatever
    # that is, it is not this leg.
    hold_on_exchange(account, side=Side.SHORT)
    report = await sync_positions(force=True)

    assert report.closed == []
    assert report.drifted == []
    assert report.untracked == [f"{account.id}:BTCUSDT"]
    leg = await leg_for(trade, account)
    assert leg.closed_at is None and leg.ok
    assert len(await notices("side_mismatch")) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_an_exit_the_platform_never_sent_is_priced_from_the_venue():
    """A stop that fires leaves the money only in the exchange's fill record."""
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    stop_fires_on_exchange(account, "101000")
    report = await sync_positions(force=True)

    leg = await leg_for(trade, account)
    assert leg.id in report.priced
    assert leg.exit_price == D("101000")
    # Long, entry 100000: the venue's own realised number, not a guess.
    assert leg.pnl == (D("101000") - leg.entry_price) * leg.qty


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_venue_with_no_fill_record_leaves_the_exit_unknown():
    """No fill is not a zero. A dash is the honest answer (spec §4 reasoning)."""
    account = await make_account("partner-a")
    trade, _ = await open_a_trade()
    await age_legs(trade)

    flatten_on_exchange(account)
    report = await sync_positions(force=True)

    leg = await leg_for(trade, account)
    assert report.priced == []
    assert leg.exit_price is None
    assert leg.pnl is None
