"""Order routing — the layer that joins the database to the fan-out engine.

Responsibilities, in order:
  1. pick the eligible accounts (spec §6: paused accounts and accounts that
     joined mid-trade sit out)
  2. build one isolated adapter per account
  3. run the fan-out (spec §4)
  4. persist the trade and every leg, including failures (spec §8)
  5. raise a persistent notification per failed leg (spec §4)
  6. push results to the panel over the WebSocket
  7. close every adapter, always

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
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Notification
from apps.core.money import D
from apps.engine.executor import (
    TradeIntent,
    amend_sltp,
    close_trade,
    failure_notifications,
    open_trade,
)
from apps.engine.fanout import FanOutResult, StopAllActive
from apps.exchanges.base import ExchangeAdapter, MarketType, OrderType, Side
from apps.exchanges.registry import build_adapter
from apps.trading import killswitch
from apps.trading.models import Trade, TradeLeg, TradeStatus

logger = logging.getLogger(__name__)


# --- account selection ------------------------------------------------------


@sync_to_async
def eligible_accounts(trade: Trade | None = None) -> list[ConnectedAccount]:
    """Accounts allowed to take part right now.

    Spec §6: an account joins from the *next* trade after it connects or
    resumes, never an in-flight one. ``eligible_from`` is set on both events,
    so the filter is a single comparison against the trade's open time.

    For a *new* entry (``trade is None``) accounts already holding a position
    are excluded as well — spec §5 allows one open trade per account, because
    each one commits 99% of that account's balance. Excluding rather than
    refusing the whole fan-out is deliberate: if one account is still winding
    down a position, that is not a reason to keep the other nine flat.
    """
    queryset = ConnectedAccount.objects.filter(status=AccountStatus.ACTIVE)
    if trade is not None:
        return list(queryset.filter(eligible_from__lte=trade.opened_at))
    return list(queryset.exclude(id__in=accounts_in_open_trades()))


def accounts_in_open_trades() -> list[int]:
    """Account ids holding a leg that filled and has not been closed (spec §5)."""
    return list(
        TradeLeg.objects.filter(
            trade__status=TradeStatus.OPEN, ok=True, closed_at__isnull=True
        ).values_list("account_id", flat=True)
    )


def _adapters(accounts: list[ConnectedAccount]) -> list[tuple[int, ExchangeAdapter]]:
    """One fresh adapter per account. Build failures become failed legs, not crashes."""
    built: list[tuple[int, ExchangeAdapter]] = []
    for account in accounts:
        try:
            built.append((account.id, build_adapter(account)))
        except Exception as exc:  # noqa: BLE001 - one bad account must not stop the rest
            logger.warning("could not build adapter for account=%s: %s", account.id, exc)
    return built


async def _close_all(adapters: list[tuple[int, ExchangeAdapter]]) -> None:
    await asyncio.gather(
        *(adapter.close() for _, adapter in adapters), return_exceptions=True
    )


# --- persistence ------------------------------------------------------------


@sync_to_async
def _persist_open(
    *, intent: TradeIntent, result: FanOutResult, accounts: list[ConnectedAccount]
) -> Trade:
    trade = Trade.objects.create(
        symbol=intent.symbol,
        side=intent.side.value,
        market=intent.market.value,
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
            )
        )
    TradeLeg.objects.bulk_create(legs)
    if fills:
        # The admin's reference entry for Q5c chart drags: the average of what
        # actually filled, not the price that was requested.
        trade.admin_entry_price = sum(fills) / len(fills)
        trade.save(update_fields=["admin_entry_price"])
    return trade


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
    now = timezone.now()
    legs = {leg.account_id: leg for leg in trade.legs.all()}
    updated = []
    for outcome in result.legs:
        leg = legs.get(outcome.account_id)
        if leg is None:
            continue
        leg.closed_at = now
        if outcome.ok and outcome.value is not None:
            leg.exit_price = outcome.value
            if leg.entry_price and leg.qty:
                direction = Decimal("1") if trade.side == Side.LONG.value else Decimal("-1")
                leg.pnl = (leg.exit_price - leg.entry_price) * leg.qty * direction
        elif leg.ok:
            # Only record a close failure for a leg that actually opened.
            # A leg that never entered will always fail to close ("no open
            # position"), and overwriting its entry error with that would hide
            # the reason the account sat out in the first place.
            leg.ok = False
            leg.error = outcome.error
            leg.error_code = outcome.error_code
        updated.append(leg)
    TradeLeg.objects.bulk_update(
        updated, ["closed_at", "exit_price", "pnl", "ok", "error", "error_code"]
    )
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


@sync_to_async
def _reference_price(symbol: str, market: MarketType) -> Decimal | None:
    """A price to size a market order with, from the public feed.

    Returns None unless the feed is **real**. When no exchange is reachable the
    market-data module serves a labelled synthetic series; that is fine for
    drawing a chart and categorically not fine for deciding how much of a
    partner's capital to commit. Adapters that can price themselves (the paper
    adapter, or any exchange where a position already exists) still work — see
    ``executor._mark_price``.
    """
    from apps.exchanges.marketdata import get_ticker

    quote = get_ticker(symbol=symbol, market=market)
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

    accounts = await eligible_accounts()
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
        reference_price=None if limit_price else await _reference_price(symbol, market),
    )
    try:
        result = await open_trade(adapters, intent)
    finally:
        await _close_all(adapters)

    trade = await _persist_open(intent=intent, result=result, accounts=accounts)
    notifications = await _persist_notifications(result)

    await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    for notification in notifications:
        await _broadcast("notification", notification)
    return trade, result


async def route_amend(
    *, trade: Trade, sl_pct: Decimal | None, tp_pct: Decimal | None
) -> FanOutResult:
    accounts = await eligible_accounts(trade)
    adapters = _adapters(accounts)
    try:
        result = await amend_sltp(
            adapters,
            symbol=trade.symbol,
            side=Side(trade.side),
            leverage=trade.leverage,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            admin_entry=trade.admin_entry_price or Decimal("0"),
        )
    finally:
        await _close_all(adapters)

    await _save_amend(trade, sl_pct, tp_pct)
    for notification in await _persist_notifications(result):
        await _broadcast("notification", notification)
    await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    return result


@sync_to_async
def _save_amend(trade: Trade, sl_pct: Decimal | None, tp_pct: Decimal | None) -> None:
    trade.sl_pct = sl_pct
    trade.tp_pct = tp_pct
    trade.save(update_fields=["sl_pct", "tp_pct"])


async def route_close(*, trade: Trade) -> FanOutResult:
    accounts = await eligible_accounts(trade)
    adapters = _adapters(accounts)
    try:
        result = await close_trade(adapters, symbol=trade.symbol)
    finally:
        await _close_all(adapters)

    await _persist_close(trade, result)
    for notification in await _persist_notifications(result):
        await _broadcast("notification", notification)
    await _broadcast("leg_result", {"trade_id": trade.id, "legs": _leg_payload(result)})
    return result


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

    try:
        result = await fan_out(
            [(aid, make(ad)) for aid, ad in adapters],
            timeout=3.0,
            respect_stop_all=False,
        )
    finally:
        await _close_all(adapters)

    rows = await _save_balances(result)
    # The consumer has carried a `balances` event since day one and nothing
    # ever sent one. This is what makes a second screen agree with the first.
    await _broadcast("balances", rows)
    return rows


def _claim_refresh_slot() -> bool:
    """True when this caller may hit the exchanges, False when one just did."""
    from django.core.cache import cache

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
    rows = []
    accounts = {a.id: a for a in ConnectedAccount.objects.filter(
        id__in=[leg.account_id for leg in result.legs]
    )}
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
        updated, ["last_balance", "last_balance_asset", "last_balance_at", "last_error"]
    )
    return rows
