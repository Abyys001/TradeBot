"""Composes sizing, SL/TP policy and the fan-out into the three admin actions.

open_trade / amend_sltp / close_trade. Each one fans out across every active
account and returns per-leg outcomes; nothing here raises because one account
failed (spec §4).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.core.money import D, floor_to_step, human
from apps.engine.fanout import FanOutResult, LegResult, fan_out
from apps.exchanges.base import (
    AdapterError,
    ExchangeAdapter,
    MarketType,
    OrderType,
    Position,
    Side,
    SLTPState,
    SymbolRules,
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
    position: Position | None = None,
    stale: list[str] | None = None,
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

    ``position`` and ``stale`` are answers the caller already has. The amend
    path reads the position to compute the trigger prices and can read the
    stale set alongside it, so both arrive here for free; taking them again
    here cost two sequential exchange round trips out of the spec §4 per-leg
    deadline — which is what pushed an amend past it on a venue answering in
    ~1s per call. ``stale=None`` means "not snapshotted yet", which is not the
    same as ``stale=[]`` ("nothing was resting").
    """
    if adapter.capabilities.native_sltp_amend:
        await adapter.set_sltp(
            symbol=symbol, stop_loss=stop_loss, take_profit=take_profit, position=position
        )
        return

    strategy = settings.TRADING["SLTP_AMEND_STRATEGY"]
    if strategy not in ("place_then_cancel", "cancel_then_place"):
        raise ValueError(f"unknown SLTP_AMEND_STRATEGY: {strategy!r}")

    if stale is None:
        stale = await adapter.list_conditional_orders(symbol)
    if strategy == "cancel_then_place":
        await adapter.cancel_orders(symbol, stale)
        await adapter.set_sltp(
            symbol=symbol, stop_loss=stop_loss, take_profit=take_profit, position=position
        )
        return

    await adapter.set_sltp(
        symbol=symbol, stop_loss=stop_loss, take_profit=take_profit, position=position
    )
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
    *,
    position: Position | None = None,
    stale: list[str] | None = None,
) -> SltpResult:
    """Place protection, then read it back in the same step.

    Raises ``AdapterError(code="sltp_mismatch")`` when the exchange did not
    hold the SL/TP that was placed — the caller decides what that means under
    its failure policy. Returns attached=True/verified=False for an exchange
    that cannot be read back (honest unconfirmed, not a lie).
    """
    await apply_sltp(
        adapter,
        symbol=symbol,
        stop_loss=stop_loss,
        take_profit=take_profit,
        position=position,
        stale=stale,
    )
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
                extra={
                    "exchange": adapter.name,
                    "error_code": getattr(exc, "code", None) or type(exc).__name__,
                },
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
        logger.error(
            "SL/TP could not be attached to %s — position is UNPROTECTED",
            intent.symbol,
            extra={"exchange": adapter.name, "error_code": "sltp_unprotected"},
        )
        return SltpResult(stop_loss, take_profit, attached=False, verified=False)
    raise ValueError(f"unknown SLTP_FAILURE_POLICY: {policy!r}")


# --- post-deadline reconciliation (Q19) ------------------------------------
#
# A failed leg is not the same thing as a leg that did nothing. ``asyncio.
# wait_for`` cancels the leg the moment the deadline passes, and the HTTP client
# gives up its own read at 0.75 of the budget (``rest.default_timeout``), but
# neither cancellation can unsend a request the exchange already received — the
# order may have executed even though we stopped listening for the reply. That
# is just as true of a 5xx, a reset connection, or an adapter error nobody has
# a code for.
#
# So the re-read runs for every leg that is ``unconfirmed`` (see
# ``fanout.NEVER_SENT_CODES``), not only for the ones that hit the deadline.
# Restricting it to ``timed_out`` was the hole: with the per-request ceiling
# *below* the fan-out deadline, a slow venue almost always raised
# ``ExchangeUnavailable: request timed out`` instead — which never reconciled,
# and reported a filled position as a failure.
#
# These helpers re-read the account on the exchange and record what actually
# happened. The exchange is the only source the platform trusts.

#: How much of the deadline a confirmation re-read may spend per leg. Floored
#: so a tiny test deadline still gets a real re-read, capped so a large
#: deadline cannot stretch the response the admin is waiting on. The ceiling
#: has to clear a real exchange round trip on a venue that is already answering
#: slowly — that is the only venue this code ever runs against.
#:
#: The amend reconcile is the demanding one: it does not merely *look*, it
#: re-applies the protection, which is a read, a place, a cancel and a
#: read-back. At 0.4 of a 10s deadline that was 4s for four round trips on a
#: venue that had just failed to answer four of them inside 10s — the re-apply
#: could not finish, and the admin got "check the position's protection" on an
#: amend that only needed a few hundred milliseconds more.
_RECONCILE_FRACTION = 0.5
_RECONCILE_FLOOR = 0.5
_RECONCILE_CEIL = 8.0


def _reconcile_budget(deadline: float) -> float:
    return min(_RECONCILE_CEIL, max(_RECONCILE_FLOOR, deadline * _RECONCILE_FRACTION))


#: ``(ok, value, error, error_code)`` for a confirmed leg, or None = unconfirmed.
Reconcile = tuple[bool, Any, str, str]

#: Appended to a leg the exchange would not answer for. The admin has to know
#: the difference between "this account did not trade" and "this account might
#: have traded and nobody can tell yet" — the second one needs them to look.
_UNVERIFIABLE = (
    " — the exchange did not answer a re-read, so it is NOT known whether this "
    "order landed: check the account on the exchange"
)


def _mark_unverifiable(leg: LegResult) -> None:
    if not leg.error.endswith(_UNVERIFIABLE):
        leg.error = f"{leg.error}{_UNVERIFIABLE}"


async def _reconcile(
    result: FanOutResult,
    accounts: list[tuple[object, ExchangeAdapter]],
    *,
    deadline: float,
    per_leg: Callable[[LegResult, ExchangeAdapter, float, float], Awaitable[Reconcile | None]],
) -> FanOutResult:
    """Ask the exchange whether each unconfirmed leg actually landed.

    Runs for every ``leg.unconfirmed`` leg whose account has an adapter, all
    concurrently, each bounded by the per-leg reconcile budget. A re-read that
    cannot answer (exchange down, overrun) returns ``None`` and the leg keeps
    the failure it already had, with a line saying the platform could not check
    — nothing here fabricates an outcome. A re-read that crashes is logged and
    treated the same way.
    """
    by_account = dict(accounts)
    pending = [leg for leg in result.legs if leg.unconfirmed and leg.account_id in by_account]
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
            _mark_unverifiable(leg)
            continue
        if outcome is None:
            _mark_unverifiable(leg)
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
    """Did an unconfirmed entry land? The exchange's position list decides.

    Before asking, wait for anything this adapter still has in the air. A leg
    cancelled at the deadline does not stop a synchronous SDK call running on a
    worker thread (``hyperliquid._call``), so the order can reach the exchange
    *after* the reconcile has already read the account. Reading first and
    concluding "no position was opened" is how a live BTC position came to be
    recorded as ``not_filled`` — a verdict in ``SAT_OUT_CODES``, which is final:
    the sweep never revisits it, close skips the leg, and the exposure sat on
    the exchange with no stop and no way to close it from the panel.
    """
    started = time.perf_counter()
    settle_budget = budget * 0.6
    try:
        settled = await adapter.settle_inflight(settle_budget)
    except Exception as exc:  # noqa: BLE001 - never worse than not having waited
        logger.warning("reconcile settle account=%s: %s", leg.account_id, exc)
        settled = False
    read_budget = max(_RECONCILE_FLOOR, budget - (time.perf_counter() - started))

    try:
        position, rules = await asyncio.wait_for(
            asyncio.gather(
                adapter.get_position(intent.symbol),
                adapter.get_symbol_rules(intent.symbol, intent.market),
            ),
            timeout=read_budget,
        )
    except TimeoutError:
        return None
    except Exception as exc:  # noqa: BLE001 - an unanswered re-read keeps the timeout
        logger.warning("reconcile open account=%s: %s", leg.account_id, exc)
        return None
    if position is None:
        if intent.order_type is not OrderType.MARKET:
            # A limit order can be resting on the exchange, live and unfilled,
            # with no position to show for it. "No position" is not "no order",
            # so this one stays unconfirmed rather than being written off.
            return None
        if not settled:
            # A request of ours is still executing. The exchange has not been
            # asked yet, so it cannot be answering — stay unconfirmed and let
            # the unbounded sweep (services.reconcile_open_trade) settle it once
            # the call has finished. An account held out of the next trade is
            # recoverable; a position nobody knows about is not.
            logger.warning(
                "reconcile account=%s: no position, but a call is still in flight — "
                "staying unconfirmed rather than declaring the entry never landed",
                leg.account_id,
                extra={"account_id": leg.account_id, "error_code": "still_in_flight"},
            )
            return None
        # Everything we sent has finished and the exchange holds nothing: the
        # order provably did not land. Say so with the original reason kept —
        # the leg is now known to have sat the entry out, which frees the
        # account for the next trade and takes it out of scope for close
        # (services.SAT_OUT_CODES).
        return (
            False,
            None,
            f"{leg.error} — re-checked with the exchange: no position was opened",
            "not_filled",
        )
    if position.side is not intent.side:
        # Someone else's position — opened by hand, or left over from something
        # this platform did not route. Claiming it as this leg's fill would put
        # a size and an entry price in the panel that belong to another trade.
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
    """Did a timed-out amend land, and is the protection what was asked for?

    Waits for anything the adapter still has in the air first, for the same
    reason ``_reconcile_open`` does and with a sharper consequence here: an
    abandoned ``set_sltp`` call is a *place*, so a snapshot taken while it is
    still on the wire misses the orders it is about to create. The Q5d cancel
    would then leave them resting alongside the pair this re-apply places, and
    the position would carry two stops — the exact state Q5d exists to prevent.
    """
    started = time.perf_counter()
    try:
        await adapter.settle_inflight(budget * 0.5)
    except Exception as exc:  # noqa: BLE001 - never worse than not having waited
        logger.warning("reconcile amend settle account=%s: %s", leg.account_id, exc)
    budget = max(_RECONCILE_FLOOR, budget - (time.perf_counter() - started))

    try:
        position, rules, stale = await asyncio.wait_for(
            _amend_reads(adapter, symbol), timeout=budget
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
            _apply_and_verify(
                adapter,
                symbol,
                risk.stop_price,
                risk.take_profit_price,
                position=position,
                stale=stale,
            ),
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


def _require_protection(sl_pct: Decimal | None, tp_pct: Decimal | None) -> None:
    """Both legs of the protection, or no order at all.

    Spec §4/§5: every account takes the same entry at the same leverage, and
    the SL/TP are what bound the loss on capital that belongs to partners. They
    are part of the order — resolved into prices per account and sent to the
    exchange — so an intent missing either is not an order this platform routes.
    """
    missing = [
        name
        for name, value in (("stop loss", sl_pct), ("take profit", tp_pct))
        if value is None
    ]
    if missing:
        raise ValueError(
            f"an order must carry both a stop loss and a take profit; missing: {', '.join(missing)}"
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

    An intent with no stop loss or no take profit is refused here, before any
    account is touched. The view already requires both, so reaching this is a
    caller building an illegal intent — and the failure has to be the whole
    trade rather than a per-leg error, because "some accounts opened
    unprotected" is the outcome the rule exists to prevent.
    """
    _require_protection(intent.sl_pct, intent.tp_pct)
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


async def confirm_open(
    accounts: list[tuple[object, ExchangeAdapter]],
    intent: TradeIntent,
    *,
    timeout: float | None = None,
) -> FanOutResult[LegFill]:
    """Re-read accounts whose entry outcome is still unknown, and settle it.

    The reconcile inside ``open_trade`` has to answer the admin's request, so
    it is bounded — an order that landed on the exchange twenty seconds after
    the deadline is past the point where it can wait. This is the same re-read
    with no order behind it, for calling later (the positions poll does), and
    it is how a fill that arrived too late to be seen still becomes a position
    the panel knows about.

    Every account passed in is treated as unconfirmed; the caller decides which
    ones those are. Legs come back exactly as ``open_trade`` would have
    reported them: ``late_fill`` for a confirmed position, ``not_filled`` when
    the exchange holds nothing, and the untouched unconfirmed leg when it will
    not answer.
    """
    deadline = timeout if timeout is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
    result: FanOutResult[LegFill] = FanOutResult(
        legs=[
            LegResult(account_id=account_id, ok=False, error="", error_code="unconfirmed")
            for account_id, _ in accounts
        ]
    )

    async def confirm(leg, adapter, budget, dl):
        return await _reconcile_open(leg, adapter, intent, budget, dl)

    return await _reconcile(result, accounts, deadline=deadline, per_leg=confirm)


async def _amend_reads(
    adapter: ExchangeAdapter, symbol: str
) -> tuple[Position | None, SymbolRules, list[str] | None]:
    """Everything an amend needs before it may place anything, in one flight.

    None of the three depends on another: the trigger prices need the position,
    the rounding needs the symbol rules, and the Q5d cancel needs the set that
    is resting *before* the new protection goes out — which running it here, at
    the very start, is exactly what guarantees.

    Serially that was three exchange round trips before the first order left.
    On Hyperliquid, answering in about a second a call, the amend spent its
    whole spec §4 per-leg budget on reads and was cancelled mid-attach: the
    admin saw "the amendment did not reach them" and the leg went on resting on
    its old stop. Concurrently the three cost one round trip.

    The stale snapshot is skipped on a venue that amends in place (Bybit,
    Toobit): ``apply_sltp`` cancels nothing there, so asking would be a round
    trip spent on an answer nobody reads. ``None`` says "not snapshotted",
    which is not ``[]`` — "nothing was resting".
    """
    calls: list[Awaitable[Any]] = [
        adapter.get_position(symbol),
        adapter.get_symbol_rules(symbol, MarketType.FUTURES),
    ]
    if not adapter.capabilities.native_sltp_amend:
        calls.append(adapter.list_conditional_orders(symbol))
    position, rules, *rest = await asyncio.gather(*calls)
    return position, rules, (rest[0] if rest else None)


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

    Both percentages are required, as they are on entry. ``apply_sltp``
    replaces the resting protection wholesale, so an amend carrying only one
    side would take the other side *off* the exchange — a "change my stop"
    that quietly deletes the take profit.
    """
    _require_protection(sl_pct, tp_pct)

    def make(account_id, adapter):
        async def op() -> SltpResult:
            position, rules, stale = await _amend_reads(adapter, symbol)
            if position is None:
                raise AdapterError(
                    "no open position on this account", code="no_position"
                )
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
                symbol,
                risk.stop_price,
                risk.take_profit_price,
                position=position,
                stale=stale,
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


@dataclass(slots=True)
class LegReduction:
    """One account's share of a scale-out, after the rounding grid has spoken."""

    account_id: object
    #: What was actually taken off, in base units.
    qty: Decimal
    #: What is left on the account afterwards.
    remaining: Decimal
    price: Decimal | None
    order_id: str = ""


async def _reduce_one(
    account_id: object,
    adapter: ExchangeAdapter,
    *,
    symbol: str,
    market: MarketType,
    side: Side,
    entry_qty: Decimal,
    target_fraction: Decimal,
) -> LegReduction:
    """Take a share off one account's position, or say why this account cannot.

    A reduce is a **reduce-only market order in the opposite direction**, not a
    sized close: ``ExchangeAdapter.close_position`` takes no size, but
    ``place_order`` has carried ``reduce_only`` since the seam was written and
    every adapter that declares the capability honours it. So a scale-out costs
    no change at the adapter layer, and reduce-only is what makes it safe —
    without it a market order the other way is a *reversal* on a venue that
    nets, and a second position on one that hedges.

    Spec §5's rounding rule is unchanged and applies to what is *kept*: the
    remainder is floored to the exchange's step, and the difference is what
    goes out. An account where either side of that lands under the exchange's
    minimum sits the scale-out out and keeps the whole position, with a
    notification — the same treatment as an account too small to take the entry.
    Rounding up to reach the minimum would exit more than the script asked for.
    """
    if not adapter.capabilities.supports_reduce_only:
        raise AdapterError(
            f"{adapter.name} cannot place a reduce-only order, so a partial exit here "
            f"would be an order to reverse the position — this account keeps the whole "
            f"position and takes the exit at the next full close",
            code="no_reduce_only",
        )

    rules, position = await asyncio.gather(
        adapter.get_symbol_rules(symbol, market), adapter.get_position(symbol)
    )
    if position is None:
        raise AdapterError(
            f"no open position on {symbol} to scale out of", code="no_position"
        )

    # The target is a share of what the *entry* filled, never of the last
    # remainder: compounding the floor at every level is how a 40/30/30 split
    # arrives at the third with a size the exchange will not accept.
    base = entry_qty if entry_qty and entry_qty > 0 else position.size
    remaining = floor_to_step(base * target_fraction, rules.qty_step)
    qty = floor_to_step(position.size - remaining, rules.qty_step)

    if qty <= 0:
        raise AdapterError(
            f"scaling to {target_fraction:%} of {human(base)} {symbol} rounds to nothing "
            f"on this exchange's {human(rules.qty_step)} step — nothing was sent",
            code="reduce_below_step",
        )
    if qty < rules.min_qty or qty * position.entry_price < rules.min_notional:
        raise AdapterError(
            f"this account's share of the exit is {human(qty)} {symbol}, below the "
            f"exchange minimum — it keeps the whole position rather than exit more "
            f"than the script asked for",
            code="reduce_below_min",
        )
    if remaining < rules.min_qty:
        raise AdapterError(
            f"the exit would leave {human(remaining)} {symbol} on this account, below "
            f"the exchange minimum, which is a remainder nothing could later close — "
            f"it keeps the whole position",
            code="remainder_below_min",
        )

    result = await adapter.place_order(
        symbol=symbol,
        market=market,
        side=Side.SHORT if side is Side.LONG else Side.LONG,
        qty=qty,
        order_type=OrderType.MARKET,
        reduce_only=True,
    )
    filled = result.filled_qty or qty
    return LegReduction(
        account_id=account_id,
        qty=filled,
        remaining=position.size - filled,
        price=result.avg_price or None,
        order_id=str(result.order_id or ""),
    )


async def reduce_trade(
    accounts: list[tuple[object, ExchangeAdapter]],
    *,
    symbol: str,
    market: MarketType,
    side: Side,
    target_fraction: Decimal,
    entry_qty: dict[object, Decimal],
    timeout: float | None = None,
) -> FanOutResult[LegReduction]:
    """A scale-out, fanned out (Q33).

    ``respect_stop_all`` is False for the same reason ``close_trade`` sets it:
    the kill switch stops *new* exposure, and this only ever lowers it.
    """
    deadline = timeout if timeout is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]

    def make(account_id, adapter):
        async def op() -> LegReduction:
            try:
                return await _reduce_one(
                    account_id,
                    adapter,
                    symbol=symbol,
                    market=market,
                    side=side,
                    entry_qty=D(entry_qty.get(account_id) or 0),
                    target_fraction=target_fraction,
                )
            except SizingRejection as exc:
                raise AdapterError(str(exc), code=exc.code) from exc

        return op

    result = await fan_out(
        [(aid, make(aid, adapter)) for aid, adapter in accounts],
        respect_stop_all=False,
        timeout=timeout,
    )

    async def confirm(leg, adapter, budget, dl):
        return await _reconcile_reduce(
            leg,
            adapter,
            symbol=symbol,
            entry_qty=D(entry_qty.get(leg.account_id) or 0),
            target_fraction=target_fraction,
            budget=budget,
            deadline=dl,
        )

    return await _reconcile(result, accounts, deadline=deadline, per_leg=confirm)


async def _reconcile_reduce(
    leg: LegResult,
    adapter: ExchangeAdapter,
    *,
    symbol: str,
    entry_qty: Decimal,
    target_fraction: Decimal,
    budget: float,
    deadline: float,
) -> Reconcile | None:
    """Did a timed-out reduce actually take the size off?

    This cannot reuse ``_reconcile_close``, which reads "the position is still
    there" as proof the close never happened. Here that is the *success* state,
    so the question is about sizes: the order landed if what is left is at or
    below the target. A position that is still full size is a reduce that did
    not happen, and the leg keeps its failure.
    """
    try:
        position = await asyncio.wait_for(adapter.get_position(symbol), timeout=budget)
    except TimeoutError:
        return None
    except Exception as exc:  # noqa: BLE001 - an unanswered re-read keeps the timeout
        logger.warning("reconcile reduce account=%s: %s", leg.account_id, exc)
        return None

    if entry_qty <= 0:
        # Nothing to measure against; an unmeasurable re-read is reported as
        # unverifiable, never as a fill.
        return None
    held = position.size if position is not None else D(0)
    target = entry_qty * target_fraction
    if held > target:
        return None

    reduction = LegReduction(
        account_id=leg.account_id,
        qty=entry_qty - held,
        remaining=held,
        price=position.entry_price if position is not None else None,
    )
    return (
        True,
        reduction,
        f"scale-out executed after the {deadline:g}s deadline — confirmed on the exchange",
        "late_reduce",
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
    "confirm_open",
    "amend_sltp",
    "close_trade",
    "reduce_trade",
    "LegReduction",
    "failure_notifications",
]
