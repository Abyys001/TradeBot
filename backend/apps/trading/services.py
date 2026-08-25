"""Order routing — the layer that joins the database to the fan-out engine.

Responsibilities, in order:
  1. pick the eligible accounts (spec §6: paused accounts and accounts that
     joined mid-trade sit out)
  2. build one isolated adapter per account
  3. run the fan-out (spec §4)
  4. persist the trade and every leg, including failures (spec §8)
  5. raise a persistent notification per failed leg (spec §4)
  6. push results to the panel over the WebSocket

Adapters are **not** closed after an action: they are kept warm per account by
``apps.exchanges.pool``, because a cold TLS handshake per leg per action was
most of the spec §4 deadline on a VPS.

Nothing here decides *policy* — sizing and SL/TP semantics live in
``apps.trading.sizing`` / ``sltp`` so they stay unit-testable without a database.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.accounts import classify, detection
from apps.accounts.models import AccountStatus, ConnectedAccount, Notification
from apps.core.money import D
from apps.engine.executor import (
    SltpResult,
    TradeIntent,
    amend_sltp,
    close_trade,
    confirm_open,
    failure_notifications,
    open_trade,
)
from apps.engine.fanout import NEVER_SENT_CODES, FanOutResult, LegResult, StopAllActive
from apps.exchanges import pool
from apps.exchanges.base import ExchangeAdapter, MarketType, OrderType, Side
from apps.trading import killswitch
from apps.trading.models import Trade, TradeLeg, TradeStatus

logger = logging.getLogger(__name__)


# --- account selection ------------------------------------------------------


#: Failure codes that prove the leg never reached ``place_order`` — the account
#: was skipped by sizing (spec §5) or by the SL/TP resolver *before* any order
#: was sent, so it holds nothing to amend or close.
#:
#: Everything **not** in this set is treated as possibly holding a position, and
#: that asymmetry is deliberate. A leg fails after a real fill on several paths
#: the engine itself documents: an entry that filled past the deadline whose
#: protection could not be confirmed (``sltp_unconfirmed``), one whose SL/TP
#: could not be attached (``sltp_failed``), a bare ``timeout``, or any adapter
#: error raised after the order went out. Those legs are recorded ``ok=False``
#: while the exchange holds a live position at leverage — filtering on ``ok``
#: made exactly those positions invisible to close, which is how a close could
#: report success while the exchange still held the trade.
#:
#: The cost of the safe direction is a leg that truly sat out being asked to
#: close, which raises "no open position" and mints one dismissable notice. A
#: spurious notice is recoverable; an unclosable position is not.
#:
#: It is the engine's ``NEVER_SENT_CODES`` — the same question ("can we prove
#: this account holds nothing?") answered once. ``not_filled`` is in it because
#: a re-read has since asked the exchange and been told no.
SAT_OUT_CODES = NEVER_SENT_CODES


def leg_is_flat(leg: TradeLeg) -> bool:
    """Can this leg be proved to hold nothing?

    Two ways, and a leg that is neither may be a live position at leverage:

    - it is already closed (``closed_at``), whether it filled or not;
    - it never opened, with a code that proves the order never reached the
      exchange (``SAT_OUT_CODES``).

    A *closed* filled leg counting as flat is the half that was missing.
    Asking only "did any leg fill?" kept a trade OPEN after every one of its
    positions had been flattened one at a time — filled-then-closed legs plus
    sat-out ones resolve to zero accounts to route, so close answered 409
    "no account could be reached" forever and the ticket stayed blocked on a
    trade no exchange held.
    """
    if leg.closed_at is not None:
        return True
    return not leg.ok and leg.error_code in SAT_OUT_CODES


@sync_to_async
def eligible_accounts(trade: Trade | None = None) -> list[ConnectedAccount]:
    """Accounts that take part in this action.

    For a *new* entry (``trade is None``): active accounts not already holding
    a position. Spec §5 allows one open trade per account, because each one
    commits 99% of that account's balance. Excluding rather than refusing the
    whole fan-out is deliberate: if one account is still winding down a
    position, that is not a reason to keep the other nine flat.

    For an amend or a close, the answer is not "who is active" but **"who may
    still be holding a leg of this trade"** — every leg that is not closed and
    did not provably sit the entry out (``SAT_OUT_CODES``). Three things follow
    from that, all of them wanted:

      - Spec §6 still holds: an account that connected or resumed after this
        trade opened has no leg in it, so it cannot join one in progress.
      - Pausing an account no longer strands its open position. Pause stops
        *new* orders; flattening or re-protecting what is already live at
        leverage is a protection action, like closing while halted (Q14).
      - A leg whose entry filled but whose protection then failed is still
        reachable by close. It is recorded ``ok=False`` — the engine says so in
        as many words ("the position is open and may be UNPROTECTED") — and
        keying eligibility on ``ok`` locked the admin out of the one position
        that most needed flattening.
    """
    if trade is not None:
        return list(
            ConnectedAccount.objects.filter(
                id__in=trade.legs.filter(closed_at__isnull=True)
                .exclude(error_code__in=SAT_OUT_CODES)
                .values_list("account_id", flat=True)
            )
        )
    return list(
        ConnectedAccount.objects.filter(status=AccountStatus.ACTIVE).exclude(
            id__in=accounts_in_open_trades()
        )
    )


def accounts_in_open_trades() -> list[int]:
    """Account ids that may be holding a leg of the open trade (spec §5).

    "May be" and not "did fill", for the same reason ``eligible_accounts``
    keeps unconfirmed legs in scope for close: a leg recorded ``ok=False``
    because the exchange never answered can still be a live position at
    leverage. Routing a second entry into that account would double it, which
    is the one thing spec §5's one-trade-per-account rule exists to prevent.

    The block is short-lived by construction — ``reconcile_open_trade`` re-reads
    those legs on every positions poll and settles them into either a real fill
    or ``not_filled`` (in ``SAT_OUT_CODES``, so the account frees itself).
    """
    open_legs = TradeLeg.objects.filter(
        trade__status=TradeStatus.OPEN, closed_at__isnull=True
    )
    return list(
        open_legs.filter(ok=True).values_list("account_id", flat=True)
    ) + list(
        open_legs.filter(ok=False)
        .exclude(error_code__in=SAT_OUT_CODES)
        .values_list("account_id", flat=True)
    )


def _adapters(accounts: list[ConnectedAccount]) -> list[tuple[int, ExchangeAdapter]]:
    """One adapter per account, warm where one already exists.

    Still one per account — the client, the credentials and the rate limiter
    are never shared, which is the structural half of spec §2 isolation. What
    changed is only that the account's own connection survives between actions
    instead of being handshaked from cold inside the §4 deadline. See
    ``apps.exchanges.pool`` for why that was most of a second on a VPS.

    Build failures become failed legs, not crashes.
    """
    built: list[tuple[int, ExchangeAdapter]] = []
    for account in accounts:
        try:
            built.append((account.id, pool.get(account)))
        except Exception as exc:  # noqa: BLE001 - one bad account must not stop the rest
            logger.warning("could not build adapter for account=%s: %s", account.id, exc)
    return built


# --- persistence ------------------------------------------------------------


@sync_to_async
def _persist_open(
    *, intent: TradeIntent, result: FanOutResult, accounts: list[ConnectedAccount]
) -> Trade:
    trade = Trade.objects.create(
        symbol=intent.symbol,
        side=intent.side.value,
        market=intent.market.value,
        order_type=intent.order_type.value,
        leverage=intent.leverage,
        sl_pct=intent.sl_pct,
        tp_pct=intent.tp_pct,
        sltp_basis=settings.TRADING["SLTP_BASIS"],
        status=TradeStatus.OPEN,
        fanout_ms=result.total_ms,
    )
    by_id = {account.id: account for account in accounts}
    fills = []
    legs = []
    for leg in result.legs:
        account = by_id.get(leg.account_id)
        if account is None:
            continue
        fill = leg.value if leg.ok else None
        if fill is not None:
            fills.append(fill.entry_price)
        legs.append(
            TradeLeg(
                trade=trade,
                account=account,
                ok=leg.ok,
                error=leg.error,
                error_code=leg.error_code,
                dispatch_ms=leg.duration_ms,
                qty=getattr(fill, "qty", None),
                entry_price=getattr(fill, "entry_price", None),
                margin=getattr(fill, "margin", None),
                stop_loss=getattr(fill, "stop_loss", None),
                take_profit=getattr(fill, "take_profit", None),
                sltp_attached=getattr(fill, "sltp_attached", False),
                sltp_verified=getattr(fill, "sltp_verified", False),
            )
        )
    TradeLeg.objects.bulk_create(legs)
    if fills:
        # The admin's reference entry for Q5c chart drags: the average of what
        # actually filled, not the price that was requested.
        trade.admin_entry_price = sum(fills) / len(fills)
        trade.save(update_fields=["admin_entry_price"])
    retire_if_nothing_open(trade)
    return trade


def retire_if_nothing_open(trade: Trade) -> bool:
    """Close a trade no account can be holding, so it stops blocking the next one.

    Every leg is one of three things: filled, *unconfirmed* (the exchange may
    have acted and has not said), or provably sat out (``SAT_OUT_CODES``). When
    a fan-out ends with no leg in the first two categories there is no position
    anywhere — every account was skipped by sizing, or overran the deadline and
    the re-read came back "no position was opened".

    Leaving that trade OPEN was a deadlock. The accounts were correctly freed
    (``accounts_in_open_trades`` ignores sat-out legs), but ``/positions/``
    still reported an open trade, so the ticket refused the next order with "a
    trade is already open" — and close could not clear it either, because
    ``eligible_accounts`` resolves the same trade to zero legs and refuses to
    send an empty fan-out. The admin was locked out by a trade that never
    existed on any exchange.

    Closed rather than deleted: spec §8 wants the failed attempt in the
    history, and the persistent §4 notices point at it.
    """
    legs = list(trade.legs.all())
    if not all(leg_is_flat(leg) for leg in legs):
        return False
    now = timezone.now()
    trade.legs.filter(closed_at__isnull=True).update(closed_at=now)
    trade.status = TradeStatus.CLOSED
    trade.closed_at = now
    trade.save(update_fields=["status", "closed_at"])
    logger.info(
        "trade=%s left no position on any account — closed instead of left open",
        trade.id,
        extra={"trade_id": trade.id},
    )
    return True


@sync_to_async
def _persist_notifications(result: FanOutResult) -> list[dict]:
    """Spec §4: one persistent notice per failed leg, cleared only by the admin."""
    payloads = failure_notifications(result)
    rows = [
        Notification(
            account_id=payload["account_id"],
            message=payload["message"],
            code=payload["code"],
        )
        for payload in payloads
    ]
    created = Notification.objects.bulk_create(rows)
    return [
        {
            "id": notification.id,
            "account_id": notification.account_id,
            "message": notification.message,
            "code": notification.code,
        }
        for notification in created
    ]


@sync_to_async
def _persist_close(trade: Trade, result: FanOutResult) -> None:
    """Record the close. The trade only reaches CLOSED when every leg is flat.

    A leg that failed to close is a position the exchange still holds, so the
    trade stays OPEN and keeps its row in the positions panel — the admin can
    see it and try again. Stamping CLOSED over a failed fan-out is what let the
    panel report a close the exchange never performed.
    """
    now = timezone.now()
    legs = {leg.account_id: leg for leg in trade.legs.all()}
    updated = []
    unflat = False
    for outcome in result.legs:
        leg = legs.get(outcome.account_id)
        if leg is None:
            continue
        # "No open position" is the exchange confirming the account is flat —
        # the desired end state, not a leg left behind.
        if not (outcome.ok or outcome.error_code == "no_position"):
            # The exchange still holds this one. Leave closed_at unset so the
            # leg stays in scope for the next close attempt, and say why.
            unflat = True
            if leg.ok:
                # Only overwrite the error of a leg that actually opened; a leg
                # that sat the entry out must keep the reason it sat out.
                leg.ok = False
                leg.error = outcome.error
                leg.error_code = outcome.error_code
                updated.append(leg)
            continue
        leg.closed_at = now
        if outcome.ok and outcome.value is not None:
            leg.exit_price = outcome.value
            if leg.entry_price and leg.qty:
                direction = Decimal("1") if trade.side == Side.LONG.value else Decimal("-1")
                leg.pnl = (leg.exit_price - leg.entry_price) * leg.qty * direction
        updated.append(leg)
    TradeLeg.objects.bulk_update(
        updated, ["closed_at", "exit_price", "pnl", "ok", "error", "error_code"]
    )
    if unflat:
        logger.error(
            "close left trade=%s open on at least one account — the exchange still "
            "holds a position; the trade stays OPEN",
            trade.id,
        )
        return
    trade.status = TradeStatus.CLOSED
    trade.closed_at = now
    trade.save(update_fields=["status", "closed_at"])


# --- broadcasting -----------------------------------------------------------


async def _broadcast(event: str, payload) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send("trading", {"type": event, "payload": payload})


def _leg_payload(result: FanOutResult) -> list[dict]:
    return [
        {
            "account_id": leg.account_id,
            "ok": leg.ok,
            "error": leg.error,
            "code": leg.error_code,
            "ms": round(leg.duration_ms, 1),
        }
        for leg in result.legs
    ]


# --- pricing ----------------------------------------------------------------


async def _no_price() -> None:
    """Stand-in so the gather above has two awaitables in both branches."""
    return None


@sync_to_async
def _reference_price(symbol: str, market: MarketType) -> Decimal | None:
    """A price to size a market order with, from the public feed.

    Returns None unless a real exchange answered. With no feed there is no
    reference price at all — nothing invents one. Adapters that can price
    themselves (the paper adapter, or any exchange where a position already
    exists) still work; see ``executor._mark_price``.
    """
    from apps.exchanges.marketdata import MarketDataError, get_ticker

    try:
        quote = get_ticker(symbol=symbol, market=market)
    except MarketDataError:
        return None
    if not quote.get("live"):
        return None
    try:
        return D(quote["price"])
    except (ValueError, KeyError):
        return None


# --- public API -------------------------------------------------------------


async def route_open(
    *,
    symbol: str,
    side: Side,
    market: MarketType,
    order_type: OrderType,
    leverage: int,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    limit_price: Decimal | None = None,
) -> tuple[Trade | None, FanOutResult]:
    # Spec §7: the runtime halt is checked here, off the event loop, before any
    # adapter is built. ``fan_out`` still checks the environment pin as a
    # backstop — that one is a plain settings read and safe to do inline.
    if await sync_to_async(killswitch.is_on)():
        raise StopAllActive("STOP_ALL is on — no orders are being routed")

    # The account list is a database read and the reference price is a network
    # call to the public feed; neither needs the other. Run in sequence they
    # were a full exchange round trip spent *before* the fan-out started, which
    # comes straight out of the §4 budget — on a cache miss that was most of it.
    accounts, reference_price = await asyncio.gather(
        eligible_accounts(),
        # A limit order carries its own price, so there is nothing to look up.
        _reference_price(symbol, market) if limit_price is None else _no_price(),
    )
    if not accounts:
        # No trade row: an empty "open" trade would sit in the history and in
        # the positions panel forever, looking like a position nobody holds.
        return None, FanOutResult(legs=[], total_ms=0.0)

    adapters = _adapters(accounts)
    intent = TradeIntent(
        symbol=symbol,
        side=side,
        market=market,
        order_type=order_type,
        leverage=leverage,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        limit_price=limit_price,
        reference_price=reference_price,
    )
    result = await open_trade(adapters, intent)

    trade = await _persist_open(intent=intent, result=result, accounts=accounts)
    notifications = await _persist_notifications(result)

    await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    for notification in notifications:
        await _broadcast("notification", notification)
    return trade, result


#: Minimum spacing between sweeps, in seconds. The positions panel polls every
#: couple of seconds and every open panel polls independently; without this,
#: one unconfirmed leg would mean a signed exchange call per tab per poll.
UNCONFIRMED_RECHECK_INTERVAL = 5
_RECHECK_GUARD_KEY = "trading:unconfirmed:checked_at"


@sync_to_async
def _unconfirmed_legs() -> tuple[Trade | None, list[ConnectedAccount]]:
    """The open trade and the accounts whose entry outcome is still unknown."""
    trade = Trade.objects.filter(status=TradeStatus.OPEN).first()
    if trade is None:
        return None, []
    accounts = list(
        ConnectedAccount.objects.filter(
            id__in=trade.legs.filter(ok=False, closed_at__isnull=True)
            .exclude(error_code__in=SAT_OUT_CODES)
            .values_list("account_id", flat=True)
        )
    )
    return trade, accounts


@sync_to_async
def _settle_unconfirmed(trade: Trade, result: FanOutResult) -> bool:
    """Write what the exchange said about each unconfirmed leg.

    A confirmed position becomes a real filled leg — size, entry, margin and
    the protection the re-read attached — so the positions panel, the totals
    and the PnL all start counting it. A leg the exchange says it holds nothing
    for is stamped ``not_filled``, which frees the account for the next trade.
    A leg that still cannot be reached is left exactly as it was.
    """
    legs = {leg.account_id: leg for leg in trade.legs.all()}
    updated = []
    fills = []
    for outcome in result.legs:
        leg = legs.get(outcome.account_id)
        if leg is None or outcome.error_code == "unconfirmed":
            continue
        fill = outcome.value
        leg.ok = outcome.ok
        leg.error = outcome.error
        leg.error_code = outcome.error_code
        if fill is not None:
            leg.qty = fill.qty
            leg.entry_price = fill.entry_price
            leg.margin = fill.margin
            leg.stop_loss = fill.stop_loss
            leg.take_profit = fill.take_profit
            leg.sltp_attached = fill.sltp_attached
            leg.sltp_verified = fill.sltp_verified
            fills.append(fill.entry_price)
        updated.append(leg)
    if not updated:
        return False
    TradeLeg.objects.bulk_update(
        updated,
        [
            "ok",
            "error",
            "error_code",
            "qty",
            "entry_price",
            "margin",
            "stop_loss",
            "take_profit",
            "sltp_attached",
            "sltp_verified",
        ],
    )
    if fills and trade.admin_entry_price is None:
        # Q5c's anchor was never set because no leg had filled at the time.
        trade.admin_entry_price = sum(fills) / len(fills)
        trade.save(update_fields=["admin_entry_price"])
    # The last unconfirmed leg may have just settled to "the exchange holds
    # nothing", which can leave this trade with nothing behind it at all.
    retire_if_nothing_open(trade)
    return True


async def reconcile_open_trade() -> bool:
    """Settle the open trade's unconfirmed legs against the exchanges.

    The reconcile inside ``open_trade`` is bounded by the admin's request: an
    entry that landed twenty seconds after the deadline is past the point where
    the response can wait for it. This is the unbounded-in-time half — cheap,
    idempotent, and called from the positions poll — so a fill that arrived too
    late to be seen still turns into a position the panel knows about, instead
    of a permanent "the exchange did not answer" note next to a live position.

    Returns True when something changed, so the caller can re-read.
    """
    if not cache.add(_RECHECK_GUARD_KEY, "1", UNCONFIRMED_RECHECK_INTERVAL):
        return False
    trade, accounts = await _unconfirmed_legs()
    if trade is None:
        return False
    if not accounts:
        # No leg is waiting on an exchange, so there is nothing to ask. If none
        # of them can be holding anything either, this trade is a ghost that
        # blocks the ticket — retire it here, on the poll, rather than leaving
        # it for a close that would resolve to zero accounts and refuse.
        return await sync_to_async(retire_if_nothing_open)(trade)
    adapters = _adapters(accounts)
    if not adapters:
        return False
    result = await confirm_open(
        adapters,
        TradeIntent(
            symbol=trade.symbol,
            side=Side(trade.side),
            market=MarketType(trade.market),
            order_type=OrderType(trade.order_type),
            leverage=trade.leverage,
            sl_pct=trade.sl_pct,
            tp_pct=trade.tp_pct,
        ),
    )
    changed = await _settle_unconfirmed(trade, result)
    if changed:
        await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    return changed


class NoLegsToRoute(Exception):
    """An amend or close resolved to zero legs, so nothing was sent.

    Never a success. An empty fan-out completes in microseconds and reports
    ``all_ok`` — which is how a close could answer 200 with an empty leg list
    while the exchange still held the position. The caller turns this into a
    refusal the admin can see instead.
    """


async def route_amend(
    *, trade: Trade, sl_pct: Decimal | None, tp_pct: Decimal | None
) -> FanOutResult:
    accounts = await eligible_accounts(trade)
    adapters = _adapters(accounts)
    if not adapters:
        raise NoLegsToRoute(
            "no account could be reached for this trade — nothing was sent to any "
            "exchange. Check the position on the exchange directly."
        )
    result = await amend_sltp(
        adapters,
        symbol=trade.symbol,
        side=Side(trade.side),
        leverage=trade.leverage,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        admin_entry=trade.admin_entry_price or Decimal("0"),
    )

    await _save_amend(trade, result, sl_pct, tp_pct)
    for notification in await _persist_notifications(result):
        await _broadcast("notification", notification)
    await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    return result


@sync_to_async
def _save_amend(
    trade: Trade,
    result: FanOutResult,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
) -> None:
    """Persist an amend. The trade carries the new percentages; each leg carries
    the prices the exchange actually holds, read back and verified per account
    — not the percentages re-derived on the DB side. A leg whose amend failed
    or timed out without confirmation keeps its old resting prices: recording
    the new ones for an account that still sits on the old stop would be the
    exact chart-vs-exchange desync this read-back exists to kill.
    """
    trade.sl_pct = sl_pct
    trade.tp_pct = tp_pct
    trade.save(update_fields=["sl_pct", "tp_pct"])

    legs = {leg.account_id: leg for leg in trade.legs.all()}
    updated = []
    for outcome in result.legs:
        leg = legs.get(outcome.account_id)
        protection = (
            outcome.value if outcome.ok and isinstance(outcome.value, SltpResult) else None
        )
        if leg is None or protection is None:
            continue
        leg.stop_loss = protection.stop_loss
        leg.take_profit = protection.take_profit
        leg.sltp_attached = protection.attached
        leg.sltp_verified = protection.verified
        updated.append(leg)
    if updated:
        TradeLeg.objects.bulk_update(
            updated, ["stop_loss", "take_profit", "sltp_attached", "sltp_verified"]
        )


@sync_to_async
def _every_account_in(trade: Trade) -> list[ConnectedAccount]:
    """Every account this trade was routed to, sat-out legs included."""
    return list(
        ConnectedAccount.objects.filter(
            id__in=trade.legs.filter(closed_at__isnull=True).values_list(
                "account_id", flat=True
            )
        )
    )


async def route_close(*, trade: Trade) -> FanOutResult:
    accounts = await eligible_accounts(trade)
    if not accounts:
        # Every leg is recorded as having sat the entry out — and that record can
        # be wrong. A leg written off as ``not_filled`` on one point-in-time read
        # is exactly how a live Hyperliquid position ended up outside the only
        # set close would look at, answering the admin 409 "no_legs" four times
        # while the exposure sat there unprotected.
        #
        # Close is the one action where being wrong the other way costs nothing:
        # ``close_position`` on a genuinely flat account answers ``no_position``,
        # which ``_settle_close`` already reads as the desired end state. So ask
        # every account the trade ever touched instead of refusing. Only close —
        # an amend aimed at a flat account would be a real failure notice.
        accounts = await _every_account_in(trade)
        if accounts:
            logger.warning(
                "close trade=%s: no leg is recorded as holding anything — asking all "
                "%d account(s) the trade was routed to anyway",
                trade.id,
                len(accounts),
                extra={"trade_id": trade.id},
            )
    adapters = _adapters(accounts)
    if not adapters:
        if await sync_to_async(retire_if_nothing_open)(trade):
            # Nothing to send *because* nothing is held: every leg is closed or
            # provably never opened. Refusing here is what locked the admin out
            # — the trade blocked the next order and close could not clear it.
            return FanOutResult(legs=[], total_ms=0.0)
        # The trade stays OPEN. Marking it closed here is precisely the bug:
        # the panel said "closed" and the exchange kept the position.
        raise NoLegsToRoute(
            "no account could be reached for this trade — nothing was sent to any "
            "exchange and the position was NOT closed. Close it on the exchange."
        )
    result = await close_trade(adapters, symbol=trade.symbol)

    await _persist_close(trade, result)
    for notification in await _persist_notifications(result):
        await _broadcast("notification", notification)
    await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    return result


@sync_to_async
def open_trades() -> list[Trade]:
    """Every trade the platform still believes is open.

    More than one can be: ``eligible_accounts`` excludes accounts already in an
    open trade, so an entry sent while account A is still in a position opens a
    *second* trade for the accounts that were free. Closing "the" open trade
    then leaves the other one live on the exchange with nobody looking at it —
    which is what ``route_close_all`` exists to prevent.
    """
    return list(Trade.objects.filter(status=TradeStatus.OPEN).order_by("id"))


async def route_close_all() -> list[tuple[Trade, FanOutResult]]:
    """Market-close **every** open trade, not just the newest one.

    Each trade is its own fan-out — an account holds at most one open trade, so
    the trades touch disjoint accounts and nothing is gained by serialising
    them. They run together for the same reason the legs inside one do: this is
    the control someone reaches for when positions have to be flat now, and N
    trades must not cost N deadlines.

    A trade that cannot be routed at all (``NoLegsToRoute``) is reported as
    itself and does not stop the others — one unreachable exchange must never
    be why the other nine stayed in the market. It also stays OPEN, because
    "nothing was sent" is not "the position is closed".
    """
    # Q22: close-all stops every running bot, for the same reason the kill
    # switch does. Flattening while a bot is still evaluating is a flatten that
    # re-enters on the next bar. Done first, so nothing can open behind the
    # close that is about to go out.
    from apps.bots.supervisor import stop_all

    await stop_all(reason="halt", detail="close-all was pressed")

    trades = await open_trades()
    if not trades:
        return []

    async def close_one(trade: Trade) -> tuple[Trade, FanOutResult]:
        try:
            return trade, await route_close(trade=trade)
        except NoLegsToRoute as exc:
            logger.error(
                "close-all trade=%s: %s", trade.id, exc, extra={"trade_id": trade.id}
            )
            return trade, FanOutResult(
                legs=[
                    LegResult(
                        account_id=leg_account_id,
                        ok=False,
                        error=str(exc),
                        error_code="no_legs",
                    )
                    for leg_account_id in await _account_ids_in(trade)
                ]
            )

    return list(await asyncio.gather(*(close_one(trade) for trade in trades)))


@sync_to_async
def _account_ids_in(trade: Trade) -> list[int]:
    """Accounts still carrying a leg of this trade, for reporting a failed close."""
    return list(
        trade.legs.filter(closed_at__isnull=True).values_list("account_id", flat=True)
    )


#: Minimum spacing between real balance fan-outs, in seconds. Every open panel
#: polls (spec §6 wants balances current, not current-when-clicked); without
#: this, five tabs would mean five times the exchange traffic for the same
#: numbers. A caller inside the window gets the stored rows instead.
BALANCE_REFRESH_INTERVAL = 20
_BALANCE_GUARD_KEY = "trading:balances:refreshed_at"


async def refresh_balances(*, force: bool = False) -> list[dict]:
    """Spec §6: the admin sees every account's balance at all times.

    Runs the same isolated-leg pattern as trading: a dead exchange delays only
    its own row. Results are pushed to every open panel over the WebSocket, so
    one poll updates every screen rather than each tab asking separately.
    """
    from apps.engine.fanout import fan_out

    if not force and not await sync_to_async(_claim_refresh_slot)():
        return await sync_to_async(_stored_balances)()

    accounts = await eligible_accounts_for_balances()
    adapters = _adapters(accounts)

    def make(adapter: ExchangeAdapter):
        async def op():
            return await adapter.get_balance()

        return op

    result = await fan_out(
        [(aid, make(ad)) for aid, ad in adapters],
        timeout=settings.TRADING["FANOUT_TIMEOUT_SECONDS"],
        respect_stop_all=False,
    )

    rows = await _save_balances(result)
    # The consumer has carried a `balances` event since day one and nothing
    # ever sent one. This is what makes a second screen agree with the first.
    await _broadcast("balances", rows)
    return rows


def _claim_refresh_slot() -> bool:
    """True when this caller may hit the exchanges, False when one just did."""
    # add() is atomic: exactly one caller wins the window, the rest read stored.
    return cache.add(_BALANCE_GUARD_KEY, True, BALANCE_REFRESH_INTERVAL)


def _stored_balances() -> list[dict]:
    """Last known balances, without asking any exchange."""
    return [
        {
            "id": account.id,
            "label": account.label,
            "balance": str(account.last_balance or ""),
            "asset": account.last_balance_asset,
            "error": account.last_error,
            "at": account.last_balance_at.isoformat() if account.last_balance_at else None,
        }
        for account in ConnectedAccount.objects.all()
    ]


async def warm_adapters() -> None:
    """Build every account's exchange client before an order needs one.

    The pool keeps an adapter warm *between* actions, but the first action
    after a restart still pays the setup — on Hyperliquid ~2.5s of TLS plus
    asset metadata, inside the spec §4 per-leg deadline, before the order is
    signed. That is a deadline blown by a client that was not ready, reported
    as an exchange that did not answer.

    Called when the panel connects (``TradingConsumer``), which is minutes
    before the admin clicks anything, and cheap to repeat: an adapter that is
    already built returns immediately.
    """
    accounts = await eligible_accounts_for_balances()
    adapters = _adapters(accounts)
    if not adapters:
        return
    await asyncio.gather(*(adapter.warm() for _, adapter in adapters), return_exceptions=True)


@sync_to_async
def eligible_accounts_for_balances() -> list[ConnectedAccount]:
    """Every connected account, paused ones included.

    Deliberately not ``eligible_accounts``: spec §6 asks for the balance of
    *every* connected account at all times, and a paused account is exactly the
    one whose balance the admin is about to check before resuming it.
    """
    return list(ConnectedAccount.objects.exclude(status=AccountStatus.ERROR))


@sync_to_async
def _save_balances(result: FanOutResult) -> list[dict]:
    now = timezone.now()
    # One instant, every account: that is what lets the classifier say "only
    # this one moved" (apps.accounts.classify). Readings taken minutes apart
    # could not be compared to each other.
    sweep = detection.Sweep(at=now)
    rows = []
    accounts = {a.id: a for a in ConnectedAccount.objects.filter(
        id__in=[leg.account_id for leg in result.legs]
    )}
    # An account holding an open leg is mid-trade, and its equity is carrying
    # unrealised PnL. The detector must not compare against that (see
    # apps.accounts.detection), so the set is read once here rather than per leg.
    busy = set(
        TradeLeg.objects.filter(
            ok=True, closed_at__isnull=True, trade__status=TradeStatus.OPEN
        ).values_list("account_id", flat=True)
    )
    updated = []
    for leg in result.legs:
        account = accounts.get(leg.account_id)
        if account is None:
            continue
        if leg.ok and leg.value is not None:
            account.last_balance = leg.value.available
            account.last_balance_asset = leg.value.asset
            account.last_balance_at = now
            account.last_error = ""
            # Q-ledger: equity, not free margin, is what a cash flow shows up
            # in. A failed read writes nothing — silence proves nothing, the
            # same rule the fan-out and possync follow.
            detection.observe(
                account,
                equity=leg.value.total,
                asset=leg.value.asset,
                flat=account.id not in busy,
                at=now,
                sweep=sweep,
            )
        else:
            account.last_error = leg.error
        updated.append(account)
        rows.append(
            {
                "id": account.id,
                "label": account.label,
                "balance": str(account.last_balance or ""),
                "asset": account.last_balance_asset,
                "error": account.last_error,
            }
        )
    ConnectedAccount.objects.bulk_update(
        updated,
        [
            "last_balance",
            "last_balance_asset",
            "last_balance_at",
            "last_error",
            *detection.FIELDS,
        ],
    )
    # After the cursors are saved, never before: a verdict may book a movement,
    # and the window it was decided from has to be on record first.
    classify.resolve_sweep(sweep)
    return rows
