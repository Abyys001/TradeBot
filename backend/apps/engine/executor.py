"""Composes sizing, SL/TP policy and the fan-out into the three admin actions.

open_trade / amend_sltp / close_trade. Each one fans out across every active
account and returns per-leg outcomes; nothing here raises because one account
failed (spec §4).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from apps.core.money import D
from apps.engine.fanout import FanOutResult, LegResult, fan_out
from apps.exchanges.base import (
    AdapterError,
    ExchangeAdapter,
    MarketType,
    OrderType,
    Side,
)
from apps.trading.sizing import SizingRejection, size_order
from apps.trading.sltp import SLTPRejection, anchor_price, resolve_active

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TradeIntent:
    """What the admin asked for, before it is resolved per account."""

    symbol: str
    side: Side
    market: MarketType
    order_type: OrderType
    leverage: int
    sl_pct: Decimal | None = None
    tp_pct: Decimal | None = None
    limit_price: Decimal | None = None
    #: Price used to size a *market* order, from the public feed. Never sent to
    #: an exchange as an order price — sizing only. The caller supplies it only
    #: when a real exchange answered (see services.route_open); nothing else may
    #: decide how much of someone's capital goes into a live trade.
    reference_price: Decimal | None = None


@dataclass(slots=True)
class LegFill:
    account_id: object
    qty: Decimal
    entry_price: Decimal
    margin: Decimal
    notional: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    sltp_attached: bool
    order_id: str


async def _open_one(
    account_id: object,
    adapter: ExchangeAdapter,
    intent: TradeIntent,
) -> LegFill:
    """One account's entry. Runs inside the fan-out's per-leg deadline."""
    # Three independent round trips, fired together: balance and rules are read
    # concurrently, and set_leverage depends on neither of them, so on a futures
    # leg it starts at the same moment instead of after them. On a venue 150ms
    # away that is ~300ms of the §4 budget handed back before anything else has
    # happened, and nothing downstream can observe the difference — the order
    # still cannot go out until every flight member has landed.
    calls = [
        adapter.get_balance(),
        adapter.get_symbol_rules(intent.symbol, intent.market),
    ]
    if intent.market is MarketType.FUTURES:
        calls.append(adapter.set_leverage(intent.symbol, intent.leverage))
    else:
        # Spot has no leverage to set; keep the tuple shape so the unpack below
        # does not depend on the market.
        calls.append(asyncio.sleep(0))
    balance, rules, leverage_call = await asyncio.gather(*calls, return_exceptions=True)

    if isinstance(balance, BaseException):
        raise balance
    if isinstance(rules, BaseException):
        raise rules

    leverage = intent.leverage
    if intent.market is MarketType.FUTURES:
        # Spec §4: leverage is identical on every account — only the dollar size
        # differs. So a cap below what the admin asked for is a *skip* with a
        # notification (the spec §5 treatment of an account that cannot comply),
        # never a silent clamp: quietly trading one partner at 5x while the rest
        # run at 10x gives them a different position for the same signal.
        cap = min(rules.max_leverage, adapter.capabilities.max_leverage)
        if leverage > cap:
            raise AdapterError(
                f"{intent.symbol} is capped at {cap}x on this account, below the "
                f"{leverage}x this trade uses — spec §4 requires identical leverage, "
                "so the account sits this one out",
                code="leverage_capped",
            )
        if isinstance(leverage_call, BaseException):
            # The cap check ran first on purpose: an account that cannot comply
            # with this leverage is skipped with the informative code, not with
            # whatever the exchange said about the rejected set_leverage.
            raise leverage_call

    reference_price = (
        intent.limit_price
        or intent.reference_price
        or (await _mark_price(adapter, intent.symbol))
    )
    sized = size_order(
        balance=balance,
        price=reference_price,
        leverage=leverage,
        rules=rules,
        market=intent.market,
    )

    risk = resolve_active(
        side=intent.side,
        entry=sized.price,
        leverage=sized.leverage,
        margin=sized.margin,
        notional=sized.notional,
        sl_pct=intent.sl_pct,
        tp_pct=intent.tp_pct,
        price_tick=rules.price_tick,
    )

    attach = adapter.capabilities.native_sltp_on_entry
    result = await adapter.place_order(
        symbol=intent.symbol,
        market=intent.market,
        side=intent.side,
        qty=sized.qty,
        order_type=intent.order_type,
        limit_price=intent.limit_price,
        stop_loss=risk.stop_price if attach else None,
        take_profit=risk.take_profit_price if attach else None,
    )

    sltp_attached = attach
    if not attach and (risk.stop_price or risk.take_profit_price):
        # Q5e: entry is filled and the position is live but unprotected. This is
        # the dangerous window; _protect applies the configured failure policy.
        sltp_attached = await _protect(adapter, intent, risk.stop_price, risk.take_profit_price)

    return LegFill(
        account_id=account_id,
        qty=result.filled_qty,
        entry_price=result.avg_price,
        margin=sized.margin,
        notional=sized.notional,
        stop_loss=risk.stop_price,
        take_profit=risk.take_profit_price,
        sltp_attached=sltp_attached,
        order_id=result.order_id,
    )


async def _mark_price(adapter: ExchangeAdapter, symbol: str) -> Decimal:
    """Last resort when no price came in with the intent.

    Order of preference: the adapter's own mark, then an existing position's
    entry. Failing both, the leg fails loudly — sizing a position off a guessed
    price is not something to do quietly with someone else's money.
    """
    mark = await adapter.get_mark_price(symbol)
    if mark:
        return mark
    position = await adapter.get_position(symbol)
    if position is not None:
        return position.entry_price
    raise AdapterError(f"no reference price available for {symbol}")


async def apply_sltp(
    adapter: ExchangeAdapter,
    *,
    symbol: str,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> None:
    """Place SL/TP, honouring the Q5d amend strategy.

    Only Bybit and the paper adapter can truly amend in place
    (``capabilities.native_sltp_amend``). Everywhere else SL/TP are ordinary
    reduce-only conditional orders, so placing new ones without cancelling the
    old ones leaves the position carrying *both*: whichever triggers first wins,
    possibly at the price the admin just replaced. That is the failure Q5d
    exists to prevent, so the cancel half happens here rather than in each
    adapter — the policy is one decision for the whole platform.

    Which side of the window to take is the configured strategy:

    ``place_then_cancel`` (Q5d's answer, default)
        New protection exists before the old is removed. The overlap is a
        moment of *double* protection — safe — at the cost of a brief window
        where a stale stop could still fire.
    ``cancel_then_place``
        No stale order can fire, at the cost of a moment with the position
        unprotected. Only sane where the exchange refuses to hold two stops.

    The stale set is snapshotted **before** placing, so the orders just placed
    are never in it. Adapters that cannot list conditional orders inherit the
    no-op default and behave exactly as before.
    """
    if adapter.capabilities.native_sltp_amend:
        await adapter.set_sltp(symbol=symbol, stop_loss=stop_loss, take_profit=take_profit)
        return

    strategy = settings.TRADING["SLTP_AMEND_STRATEGY"]
    if strategy not in ("place_then_cancel", "cancel_then_place"):
        raise ValueError(f"unknown SLTP_AMEND_STRATEGY: {strategy!r}")

    stale = await adapter.list_conditional_orders(symbol)
    if strategy == "cancel_then_place":
        await adapter.cancel_orders(symbol, stale)
        await adapter.set_sltp(symbol=symbol, stop_loss=stop_loss, take_profit=take_profit)
        return

    await adapter.set_sltp(symbol=symbol, stop_loss=stop_loss, take_profit=take_profit)
    if stale:
        # The new orders are live; the old ones are now the dangerous half.
        # A failure here is loud: a stale stop at a replaced price is exactly
        # what the admin thinks they just cancelled.
        await adapter.cancel_orders(symbol, stale)


async def _protect(
    adapter: ExchangeAdapter,
    intent: TradeIntent,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> bool:
    """Attach SL/TP after entry, applying the Q5e failure policy.

    Returns True when the position ended up protected. When it did not and the
    policy says so, the position is closed at market rather than left running
    unprotected at leverage.
    """
    retries = settings.TRADING["SLTP_FAILURE_RETRIES"]
    policy = settings.TRADING["SLTP_FAILURE_POLICY"]
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            await apply_sltp(
                adapter, symbol=intent.symbol, stop_loss=stop_loss, take_profit=take_profit
            )
            return True
        except AdapterError as exc:
            last_error = exc
            logger.warning(
                "SL/TP attach failed symbol=%s attempt=%s/%s: %s",
                intent.symbol,
                attempt + 1,
                retries + 1,
                exc,
            )

    if policy == "retry_then_close":
        logger.error(
            "SL/TP could not be attached to %s — closing at market (policy=%s)",
            intent.symbol,
            policy,
        )
        await adapter.close_position(intent.symbol)
        raise AdapterError(
            f"SL/TP could not be attached ({last_error}); position closed at market"
        )
    if policy == "close_immediately":
        await adapter.close_position(intent.symbol)
        raise AdapterError(f"SL/TP attach failed ({last_error}); position closed at market")
    if policy == "retry_then_notify":
        logger.error("SL/TP could not be attached to %s — position is UNPROTECTED", intent.symbol)
        return False
    raise ValueError(f"unknown SLTP_FAILURE_POLICY: {policy!r}")


async def open_trade(
    accounts: list[tuple[object, ExchangeAdapter]],
    intent: TradeIntent,
    *,
    timeout: float | None = None,
) -> FanOutResult[LegFill]:
    """Entry, fanned out. Sizing rejections are per-account, never global.

    ``timeout`` overrides the configured per-leg deadline; the tests use it to
    keep a hung-leg scenario quick without changing the platform's setting.
    """
    return await fan_out(
        [(aid, _make_open(aid, adapter, intent)) for aid, adapter in accounts],
        timeout=timeout,
    )


def _make_open(account_id, adapter, intent):
    async def op() -> LegFill:
        try:
            return await _open_one(account_id, adapter, intent)
        except (SizingRejection, SLTPRejection) as exc:
            # Carry the machine-readable code up so the UI can distinguish
            # "too small to trade" from "the exchange broke".
            raise AdapterError(str(exc), code=exc.code) from exc

    return op


async def amend_sltp(
    accounts: list[tuple[object, ExchangeAdapter]],
    *,
    symbol: str,
    side: Side,
    leverage: int,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    admin_entry: Decimal,
    timeout: float | None = None,
) -> FanOutResult[None]:
    """Mid-trade SL/TP change (spec §4 — must land within the fan-out deadline).

    ``respect_stop_all`` is False for the same reason as ``close_trade``: Q14
    decided the halt stops *new* routing only. Tightening a stop on a position
    that is already live at leverage is a protection action, and the panel's
    own copy promises it keeps working while halted.
    """

    def make(account_id, adapter):
        async def op() -> None:
            # Two independent reads, so they travel together rather than back to
            # back — one full exchange round trip handed back to the §4 budget
            # on every amend. The position lookup cannot short-circuit the rules
            # read, but that read is harmless when no position exists.
            position, rules = await asyncio.gather(
                adapter.get_position(symbol),
                adapter.get_symbol_rules(symbol, MarketType.FUTURES),
            )
            if position is None:
                raise AdapterError("no open position on this account")
            # Q5b/Q5c: which entry price the percentage is measured from.
            entry = anchor_price(admin_entry=admin_entry, own_entry=position.entry_price)
            # The exchange's own view of this position's leverage, not the
            # admin's requested number: the two can differ if the exchange
            # capped it, and margin computed off the wrong one moves the stop.
            effective_leverage = position.leverage or leverage
            risk = resolve_active(
                side=side,
                entry=entry,
                leverage=effective_leverage,
                margin=position.size * position.entry_price / D(effective_leverage),
                notional=position.size * position.entry_price,
                sl_pct=sl_pct,
                tp_pct=tp_pct,
                price_tick=rules.price_tick,
            )
            await apply_sltp(
                adapter,
                symbol=symbol,
                stop_loss=risk.stop_price,
                take_profit=risk.take_profit_price,
            )

        return op

    return await fan_out(
        [(aid, make(aid, ad)) for aid, ad in accounts],
        respect_stop_all=False,
        timeout=timeout,
    )


async def close_trade(
    accounts: list[tuple[object, ExchangeAdapter]],
    *,
    symbol: str,
    timeout: float | None = None,
) -> FanOutResult[Decimal]:
    """Market-close everywhere (spec §3, §4).

    respect_stop_all is False on purpose: the kill switch stops *new* routing,
    it must never prevent the admin from flattening open positions.
    """

    def make(adapter):
        async def op() -> Decimal:
            result = await adapter.close_position(symbol)
            return result.avg_price

        return op

    return await fan_out(
        [(aid, make(ad)) for aid, ad in accounts],
        respect_stop_all=False,
        timeout=timeout,
    )


def failure_notifications(result: FanOutResult) -> list[dict]:
    """Spec §4: one persistent notification per failed leg, dismissed manually."""
    return [
        {
            "account_id": leg.account_id,
            "message": leg.error,
            "code": leg.error_code,
            "duration_ms": round(leg.duration_ms, 1),
            "persistent": True,
        }
        for leg in result.failed
    ]


__all__ = [
    "TradeIntent",
    "LegFill",
    "LegResult",
    "open_trade",
    "amend_sltp",
    "close_trade",
    "failure_notifications",
]
