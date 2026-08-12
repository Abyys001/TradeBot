"""Composes sizing, SL/TP policy and the fan-out into the three admin actions.

open_trade / amend_sltp / close_trade. Each one fans out across every active
account and returns per-leg outcomes; nothing here raises because one account
failed (spec §4).
"""

from __future__ import annotations

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
    #: when the feed is real (see services.route_open); a synthetic price must
    #: never decide how much of someone's capital goes into a live trade.
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
    balance = await adapter.get_balance()
    rules = await adapter.get_symbol_rules(intent.symbol, intent.market)

    leverage = min(intent.leverage, rules.max_leverage, adapter.capabilities.max_leverage)
    if intent.market is MarketType.FUTURES:
        await adapter.set_leverage(intent.symbol, leverage)

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
            await adapter.set_sltp(
                symbol=intent.symbol, stop_loss=stop_loss, take_profit=take_profit
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
) -> FanOutResult[LegFill]:
    """Entry, fanned out. Sizing rejections are per-account, never global."""
    return await fan_out(
        [(aid, _make_open(aid, adapter, intent)) for aid, adapter in accounts]
    )


def _make_open(account_id, adapter, intent):
    async def op() -> LegFill:
        try:
            return await _open_one(account_id, adapter, intent)
        except (SizingRejection, SLTPRejection) as exc:
            # Carry the machine-readable code up so the UI can distinguish
            # "too small to trade" from "the exchange broke".
            raise AdapterError(str(exc)) from exc

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
) -> FanOutResult[None]:
    """Mid-trade SL/TP change (spec §4 — must land within 1 second)."""

    def make(account_id, adapter):
        async def op() -> None:
            position = await adapter.get_position(symbol)
            if position is None:
                raise AdapterError("no open position on this account")
            rules = await adapter.get_symbol_rules(symbol, MarketType.FUTURES)
            # Q5b/Q5c: which entry price the percentage is measured from.
            entry = anchor_price(admin_entry=admin_entry, own_entry=position.entry_price)
            risk = resolve_active(
                side=side,
                entry=entry,
                leverage=leverage,
                margin=position.size * position.entry_price / D(leverage),
                notional=position.size * position.entry_price,
                sl_pct=sl_pct,
                tp_pct=tp_pct,
                price_tick=rules.price_tick,
            )
            await adapter.set_sltp(
                symbol=symbol,
                stop_loss=risk.stop_price,
                take_profit=risk.take_profit_price,
            )

        return op

    return await fan_out([(aid, make(aid, ad)) for aid, ad in accounts])


async def close_trade(
    accounts: list[tuple[object, ExchangeAdapter]],
    *,
    symbol: str,
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
