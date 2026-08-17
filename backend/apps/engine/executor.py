"""Composes sizing, SL/TP policy and the fan-out into the three admin actions.

open_trade / amend_sltp / close_trade. Each one fans out across every active
account and returns per-leg outcomes; nothing here raises because one account
failed (spec §4).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.core.money import D
from apps.engine.fanout import FanOutResult, LegResult, fan_out
from apps.exchanges.base import (
    AdapterError,
    ExchangeAdapter,
    MarketType,
    OrderType,
    Side,
    SLTPState,
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
    sltp_verified: bool
    order_id: str


@dataclass(frozen=True, slots=True)
class SltpResult:
    """What protection is actually resting on the exchange, after a read-back.

    ``attached`` and ``verified`` are deliberately two flags. ``attached`` is
    the outcome the caller acts on: when False the position is unprotected and
    the Q5e policy says what happens next. ``verified`` is how much we can
    trust that outcome: an exchange with no ``get_sltp`` read-back is recorded
    as placed-but-unconfirmed rather than certified, so a silently dropped
    trigger order can never masquerade as protection.
    """

    stop_loss: Decimal | None
    take_profit: Decimal | None
    attached: bool
    verified: bool


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

    if risk.stop_price or risk.take_profit_price:
        if attach:
            # Entry carried the SL/TP natively. Placing is not proof — an
            # exchange can silently drop a trigger leg — so read the protection
            # back. On a mismatch the Q5e path re-attaches (place-then-cancel
            # clears the wrong order along the way) instead of trusting the
            # fill's side effects.
            state, ok = await _verify_sltp(
                adapter, intent.symbol, risk.stop_price, risk.take_profit_price
            )
            if state is not None and not ok:
                logger.warning(
                    "native SL/TP read back as stop=%s take-profit=%s on %s — re-attaching",
                    state.stop_loss,
                    state.take_profit,
                    intent.symbol,
                )
                protection = await _protect(
                    adapter, intent, risk.stop_price, risk.take_profit_price
                )
            else:
                protection = SltpResult(
                    stop_loss=risk.stop_price,
                    take_profit=risk.take_profit_price,
                    attached=True,
                    verified=state is not None,
                )
        else:
            # Q5e: entry is filled and the position is live but unprotected. This
            # is the dangerous window; _protect applies the configured policy.
            protection = await _protect(adapter, intent, risk.stop_price, risk.take_profit_price)
    else:
        protection = SltpResult(None, None, attached=attach, verified=False)

    return LegFill(
        account_id=account_id,
        qty=result.filled_qty,
        entry_price=result.avg_price,
        margin=sized.margin,
        notional=sized.notional,
        stop_loss=protection.stop_loss,
        take_profit=protection.take_profit,
        sltp_attached=protection.attached,
        sltp_verified=protection.verified,
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


#: How close a read-back trigger price must be to what was placed. Read-back
#: prices come back re-rounded by each exchange's own grid (Hyperliquid rounds
#: triggers to five significant figures, say), so exact equality is the wrong
#: test — but the band must be tight enough that it can never certify a stop at
#: the wrong price.
_SLTP_TOLERANCE = D("0.0001")


def _prices_close(a: Decimal | None, b: Decimal | None) -> bool:
    """Two trigger prices agree within the exchange's rounding."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a == b:
        return True
    span = max(abs(a), abs(b))
    return abs(a - b) <= span * _SLTP_TOLERANCE


async def _verify_sltp(
    adapter: ExchangeAdapter,
    symbol: str,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> tuple[SLTPState | None, bool]:
    """Read the protection back from the exchange and judge it.

    ``(state, ok)``. ``state`` is None when the adapter cannot answer — a read
    error or a missing ``get_sltp`` endpoint — and that is never a failure:
    ok stays True so the leg records placed-but-unconfirmed rather than
    alarming the admin over an exchange the platform cannot hold to account.
    When the adapter can answer, every requested leg must be present and
    price-close, or the exchange is not honouring what was placed.
    """
    try:
        state = await adapter.get_sltp(symbol)
    except Exception as exc:  # noqa: BLE001 - an unanswerable read-back is "cannot ask"
        logger.warning("SL/TP read-back failed for %s: %s", symbol, exc)
        return None, True
    if state is None:
        return None, True
    ok = _prices_close(state.stop_loss, stop_loss) and _prices_close(
        state.take_profit, take_profit
    )
    return state, ok


async def _apply_and_verify(
    adapter: ExchangeAdapter,
    symbol: str,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> SltpResult:
    """Place protection, then read it back in the same step.

    Raises ``AdapterError(code="sltp_mismatch")`` when the exchange did not
    hold the SL/TP that was placed — the caller decides what that means under
    its failure policy. Returns attached=True/verified=False for an exchange
    that cannot be read back (honest unconfirmed, not a lie).
    """
    await apply_sltp(adapter, symbol=symbol, stop_loss=stop_loss, take_profit=take_profit)
    state, ok = await _verify_sltp(adapter, symbol, stop_loss, take_profit)
    if state is None:
        return SltpResult(stop_loss, take_profit, attached=True, verified=False)
    if ok:
        return SltpResult(stop_loss, take_profit, attached=True, verified=True)
    raise AdapterError(
        "the exchange did not hold the SL/TP that was placed: "
        f"read back stop={state.stop_loss} take-profit={state.take_profit}",
        code="sltp_mismatch",
    )


async def _protect(
    adapter: ExchangeAdapter,
    intent: TradeIntent,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> SltpResult:
    """Attach SL/TP after entry, applying the Q5e failure policy.

    ``attached`` is only True when the read-back confirms the protection
    actually rests on the exchange (``verified``); an adapter that cannot be
    read back is recorded as placed-but-unconfirmed so a silent drop can never
    masquerade as a protected leg. When protection could not be attached and
    the policy says so, the position is closed at market rather than left
    running unprotected at leverage.
    """
    retries = settings.TRADING["SLTP_FAILURE_RETRIES"]
    policy = settings.TRADING["SLTP_FAILURE_POLICY"]
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            return await _apply_and_verify(
                adapter, intent.symbol, stop_loss, take_profit
            )
        except AdapterError as exc:
            last_error = exc
            logger.warning(
                "SL/TP attach failed symbol=%s attempt=%s/%s: %s",
                intent.symbol,
                attempt + 1,
                retries + 1,
                exc,
                extra={"exchange": adapter.name, "error_code": getattr(exc, "code", None) or type(exc).__name__},
            )

    if policy == "retry_then_close":
        logger.error(
            "SL/TP could not be attached to %s — closing at market (policy=%s)",
            intent.symbol,
            policy,
            extra={"exchange": adapter.name, "error_code": "sltp_failed"},
        )
        await adapter.close_position(intent.symbol)
        raise AdapterError(
            f"SL/TP could not be attached ({last_error}); position closed at market"
        )
    if policy == "close_immediately":
        await adapter.close_position(intent.symbol)
        raise AdapterError(f"SL/TP attach failed ({last_error}); position closed at market")
    if policy == "retry_then_notify":
        logger.error("SL/TP could not be attached to %s — position is UNPROTECTED", intent.symbol, extra={"exchange": adapter.name, "error_code": "sltp_unprotected"})
        return SltpResult(stop_loss, take_profit, attached=False, verified=False)
    raise ValueError(f"unknown SLTP_FAILURE_POLICY: {policy!r}")


# --- post-deadline reconciliation (Q19) ------------------------------------
#
# A timed-out leg is *unconfirmed*, not failed. ``asyncio.wait_for`` cancels the
# leg the moment the deadline passes, but cancellation cannot unsend a request
# the exchange already received — the order may have executed even though we
# stopped listening for the reply. These helpers re-read the account on the
# exchange and record what actually happened, so a note that says "exceeded the
# deadline" is never minted for a position that demonstrably exists on the
# other side. The exchange is the only source the platform trusts.

#: How much of the deadline a confirmation re-read may spend per leg. Floored
#: so a tiny test deadline still gets a real re-read, capped so a large
#: deadline cannot stretch the response the admin is waiting on.
_RECONCILE_FRACTION = 0.4
_RECONCILE_FLOOR = 0.5
_RECONCILE_CEIL = 2.0


def _reconcile_budget(deadline: float) -> float:
    return min(_RECONCILE_CEIL, max(_RECONCILE_FLOOR, deadline * _RECONCILE_FRACTION))


#: ``(ok, value, error, error_code)`` for a confirmed leg, or None = unconfirmed.
Reconcile = tuple[bool, Any, str, str]


async def _reconcile(
    result: FanOutResult,
    accounts: list[tuple[object, ExchangeAdapter]],
    *,
    deadline: float,
    per_leg: Callable[[LegResult, ExchangeAdapter, float, float], Awaitable[Reconcile | None]],
) -> FanOutResult:
    """Ask the exchange whether each timed-out leg actually landed.

    Runs only for ``leg.timed_out`` legs whose account has an adapter, all
    concurrently, each bounded by the per-leg reconcile budget. A re-read that
    cannot answer (no position, exchange down, overrun) returns ``None`` and
    the leg keeps its timeout — nothing here fabricates an outcome. A re-read
    that crashes is logged and treated the same way.
    """
    by_account = dict(accounts)
    pending = [leg for leg in result.legs if leg.timed_out and leg.account_id in by_account]
    if not pending:
        return result

    budget = _reconcile_budget(deadline)
    outcomes = await asyncio.gather(
        *(per_leg(leg, by_account[leg.account_id], budget, deadline) for leg in pending),
        return_exceptions=True,
    )
    for leg, outcome in zip(pending, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            logger.warning("reconcile crashed for account=%s: %s", leg.account_id, outcome)
            continue
        if outcome is None:
            continue
        ok, value, error, error_code = outcome
        logger.info("reconcile account=%s -> ok=%s (%s)", leg.account_id, ok, error_code)
        leg.ok = ok
        leg.value = value
        leg.error = error
        leg.error_code = error_code
    return result


async def _reconcile_open(
    leg: LegResult,
    adapter: ExchangeAdapter,
    intent: TradeIntent,
    budget: float,
    deadline: float,
) -> Reconcile | None:
    """Did a timed-out entry land? The exchange's position list decides."""
    try:
        position, rules = await asyncio.wait_for(
            asyncio.gather(
                adapter.get_position(intent.symbol),
                adapter.get_symbol_rules(intent.symbol, intent.market),
            ),
            timeout=budget,
        )
    except TimeoutError:
        return None
    except Exception as exc:  # noqa: BLE001 - an unanswered re-read keeps the timeout
        logger.warning("reconcile open account=%s: %s", leg.account_id, exc)
        return None
    if position is None:
        return None

    leverage = position.leverage or intent.leverage
    notional = position.size * position.entry_price
    margin = notional if intent.market is MarketType.SPOT else notional / D(leverage)
    risk = resolve_active(
        side=intent.side,
        entry=position.entry_price,
        leverage=leverage,
        margin=margin,
        notional=notional,
        sl_pct=intent.sl_pct,
        tp_pct=intent.tp_pct,
        price_tick=rules.price_tick,
    )

    # On an exchange without native entry SL/TP the fill is real but the
    # protection never ran. Close that window the way the normal path does
    # (Q5e), inside the reconcile budget — but never more than one bounded
    # attempt: the leg already overran and the response must stay bounded.
    attached = adapter.capabilities.native_sltp_on_entry
    verified = False
    if risk.stop_price or risk.take_profit_price:
        if attached:
            # Native entry carried the protection; confirm it survived the ride.
            # A read-back we cannot get in the remaining budget is unconfirmed,
            # never a reason to fabricate a failure for a real position.
            try:
                state, ok = await asyncio.wait_for(
                    _verify_sltp(
                        adapter, intent.symbol, risk.stop_price, risk.take_profit_price
                    ),
                    timeout=budget,
                )
                verified = state is not None and ok
            except TimeoutError:
                verified = False
        else:
            try:
                protection = await asyncio.wait_for(
                    _apply_and_verify(
                        adapter,
                        intent.symbol,
                        risk.stop_price,
                        risk.take_profit_price,
                    ),
                    timeout=budget,
                )
                attached, verified = protection.attached, protection.verified
            except TimeoutError:
                return (
                    False,
                    None,
                    "entry filled after the deadline but the SL/TP attach was cut off — "
                    "the position is open and may be UNPROTECTED: check it now",
                    "sltp_unconfirmed",
                )
            except AdapterError as exc:
                if settings.TRADING["SLTP_FAILURE_POLICY"] == "retry_then_notify":
                    return (
                        False,
                        None,
                        "entry filled after the deadline but SL/TP could not be attached — "
                        "the position is UNPROTECTED",
                        "sltp_failed",
                    )
                try:
                    await asyncio.wait_for(adapter.close_position(intent.symbol), timeout=budget)
                except TimeoutError:
                    logger.error(
                        "reconcile: SL/TP attach failed on %s and the position could not be "
                        "closed either — open and UNPROTECTED",
                        intent.symbol,
                    )
                    return (
                        False,
                        None,
                        "entry filled after the deadline, SL/TP could not be attached and the "
                        "position could not be closed — it is open and UNPROTECTED: check it now",
                        "sltp_unconfirmed",
                    )
                except Exception as close_exc:  # noqa: BLE001
                    logger.error(
                        "reconcile close after failed attach on %s: %s", intent.symbol, close_exc
                    )
                    return (
                        False,
                        None,
                        f"entry filled after the deadline, SL/TP could not be attached ({exc}) "
                        f"and closing the position also failed ({close_exc}) — it is open and "
                        "UNPROTECTED: check it now",
                        "sltp_unconfirmed",
                    )
                return (
                    False,
                    None,
                    f"entry filled after the deadline but SL/TP could not be attached ({exc}); "
                    "position closed at market",
                    "closed_after_late_fill",
                )

    return (
        True,
        LegFill(
            account_id=leg.account_id,
            qty=position.size,
            entry_price=position.entry_price,
            margin=margin,
            notional=notional,
            stop_loss=risk.stop_price,
            take_profit=risk.take_profit_price,
            sltp_attached=attached,
            sltp_verified=verified,
            order_id="",
        ),
        f"entry filled after the {deadline:g}s deadline — confirmed on the exchange",
        "late_fill",
    )


async def _reconcile_close(
    leg: LegResult,
    adapter: ExchangeAdapter,
    symbol: str,
    budget: float,
    deadline: float,
) -> Reconcile | None:
    """Did a timed-out close actually flatten the position?"""
    try:
        position = await asyncio.wait_for(adapter.get_position(symbol), timeout=budget)
    except TimeoutError:
        return None
    except Exception as exc:  # noqa: BLE001 - an unanswered re-read keeps the timeout
        logger.warning("reconcile close account=%s: %s", leg.account_id, exc)
        return None
    if position is not None:
        # Still there — the close genuinely did not happen.
        return None
    try:
        mark = await asyncio.wait_for(adapter.get_mark_price(symbol), timeout=budget)
    except Exception:  # noqa: BLE001 - the close is the fact; the price is a detail
        mark = None
    return (
        True,
        mark,
        f"close executed after the {deadline:g}s deadline — confirmed on the exchange",
        "late_close",
    )


async def _reconcile_amend(
    leg: LegResult,
    adapter: ExchangeAdapter,
    *,
    symbol: str,
    side: Side,
    leverage: int,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    admin_entry: Decimal,
    budget: float,
    deadline: float,
) -> Reconcile | None:
    """Did a timed-out amend land, and is the protection what was asked for?"""
    try:
        position, rules = await asyncio.wait_for(
            asyncio.gather(
                adapter.get_position(symbol),
                adapter.get_symbol_rules(symbol, MarketType.FUTURES),
            ),
            timeout=budget,
        )
    except TimeoutError:
        return None
    except Exception as exc:  # noqa: BLE001 - an unanswered re-read keeps the timeout
        logger.warning("reconcile amend account=%s: %s", leg.account_id, exc)
        return None
    if position is None:
        # Nothing left to amend — the position closed (at its old stop, say)
        # while the amend was in flight. The amend is moot, not a failure.
        return (
            True,
            None,
            "position already closed on the exchange — the SL/TP amend no longer applies",
            "position_closed",
        )
    entry = anchor_price(admin_entry=admin_entry, own_entry=position.entry_price)
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
    try:
        protection = await asyncio.wait_for(
            _apply_and_verify(adapter, symbol, risk.stop_price, risk.take_profit_price),
            timeout=budget,
        )
    except TimeoutError:
        return (
            False,
            None,
            "SL/TP amend could not be re-applied after the deadline — check the "
            "position's protection",
            "sltp_unconfirmed",
        )
    except AdapterError as exc:
        return (
            False,
            None,
            f"SL/TP amend could not be re-applied after the deadline: {exc}",
            "sltp_failed",
        )
    return (
        True,
        protection,
        f"SL/TP re-applied after the {deadline:g}s deadline — confirmed on the exchange",
        "late_amend",
    )


async def open_trade(
    accounts: list[tuple[object, ExchangeAdapter]],
    intent: TradeIntent,
    *,
    timeout: float | None = None,
) -> FanOutResult[LegFill]:
    """Entry, fanned out. Sizing rejections are per-account, never global.

    ``timeout`` overrides the configured per-leg deadline; the tests use it to
    keep a hung-leg scenario quick without changing the platform's setting.
    Legs that hit the deadline are re-read from the exchange afterwards
    (``_reconcile_open``): an entry that demonstrably landed is reported as
    filled — with a note saying so, never as a timeout failure.
    """
    deadline = timeout if timeout is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
    result = await fan_out(
        [(aid, _make_open(aid, adapter, intent)) for aid, adapter in accounts],
        timeout=timeout,
    )

    async def confirm(leg, adapter, budget, dl):
        return await _reconcile_open(leg, adapter, intent, budget, dl)

    return await _reconcile(result, accounts, deadline=deadline, per_leg=confirm)


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
) -> FanOutResult[SltpResult]:
    """Mid-trade SL/TP change (spec §4 — must land within the fan-out deadline).

    Each leg returns its ``SltpResult`` — what the exchange actually holds
    after the amend, verified by read-back where the adapter can answer — so
    the caller persists real resting prices per leg instead of the admin's
    percentages.

    ``respect_stop_all`` is False for the same reason as ``close_trade``: Q14
    decided the halt stops *new* routing only. Tightening a stop on a position
    that is already live at leverage is a protection action, and the panel's
    own copy promises it keeps working while halted.
    """

    def make(account_id, adapter):
        async def op() -> SltpResult:
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
            return await _apply_and_verify(
                adapter,
                symbol=symbol,
                stop_loss=risk.stop_price,
                take_profit=risk.take_profit_price,
            )

        return op

    deadline = timeout if timeout is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
    result = await fan_out(
        [(aid, make(aid, ad)) for aid, ad in accounts],
        respect_stop_all=False,
        timeout=timeout,
    )

    async def confirm(leg, adapter, budget, dl):
        return await _reconcile_amend(
            leg,
            adapter,
            symbol=symbol,
            side=side,
            leverage=leverage,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            admin_entry=admin_entry,
            budget=budget,
            deadline=dl,
        )

    return await _reconcile(result, accounts, deadline=deadline, per_leg=confirm)


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

    deadline = timeout if timeout is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
    result = await fan_out(
        [(aid, make(ad)) for aid, ad in accounts],
        respect_stop_all=False,
        timeout=timeout,
    )

    async def confirm(leg, adapter, budget, dl):
        return await _reconcile_close(leg, adapter, symbol, budget, dl)

    return await _reconcile(result, accounts, deadline=deadline, per_leg=confirm)


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
    "SltpResult",
    "LegResult",
    "open_trade",
    "amend_sltp",
    "close_trade",
    "failure_notifications",
]
