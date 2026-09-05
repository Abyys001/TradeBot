"""One asyncio task per running bot, in the process that owns the fan-out.

In the ASGI process alongside the engine, not behind a broker: a bot's actions
go through ``services.route_*``, which is async and carries the spec §4 per-leg
deadline, and a broker round trip plus worker prefetch spends most of that
budget before the first exchange call. ``BOT_SUPERVISOR_IN_ASGI=false`` moves it
to the ``bots`` compose service instead, for a deployment that wants the
separation; the loop is identical either way.

**Isolation between bots is the same promise as isolation between accounts.**
One bot's exception, one bot's slow script, one bot's dead feed touches no other:
per-task supervision, every exception caught at the task boundary, and never a
``gather`` without ``return_exceptions=True``.

The loop, in order, and the order is the argument:

    next confirmed bar → run_bar → intent → reconcile against the exchange
    → translate → risk gate → dispatch → persist → broadcast

Reconciling *before* the diff is the part that is easy to get wrong. The exchange
decides what is open, not this database; a stop that fired on the venue, a
liquidation, or a close performed in the venue's own app all change the position
with no request from here. Diffing against a stale record re-enters a position
the bot already has, or closes one it does not.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from decimal import Decimal

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.bots import recovery as recovery_module
from apps.bots import retention, translate
from apps.bots.config import limits
from apps.bots.feed import BarFeed, ClockSkew, FeedGap, NotEnoughHistory
from apps.bots.models import Bot, BotAction, BotBar, BotRun, BotState, StopReason
from apps.bots.riskgate import RiskGate
from apps.exchanges.base import MarketType
from apps.logging.utils import system_log
from apps.pine.errors import PineError, PineRuntimeError
from apps.pine.intent import Side
from apps.pine.runtime import Runtime
from apps.pine.symbol import SymbolInfo, TimeframeInfo
from apps.pine.validate import validate

ZERO = Decimal("0")

logger = logging.getLogger(__name__)

#: bot id → its task. The single registry; nothing else tracks running bots.
_TASKS: dict[int, asyncio.Task] = {}
_LOCK = asyncio.Lock()


# --- broadcasting -----------------------------------------------------------


async def _broadcast(event: str, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send("trading", {"type": event, "payload": payload})


# --- public control surface -------------------------------------------------


def running_ids() -> set[int]:
    return {bot_id for bot_id, task in _TASKS.items() if not task.done()}


async def start(bot: Bot) -> BotRun:
    """Start (or resume) ``bot``. Idempotent — starting a running bot is a no-op."""
    async with _LOCK:
        existing = _TASKS.get(bot.id)
        if existing is not None and not existing.done():
            return await _open_run(bot)
        run = await _open_run(bot)
        task = asyncio.create_task(_supervise(bot.id, run.id), name=f"bot-{bot.id}")
        _TASKS[bot.id] = task
        return run


async def stop(bot_id: int, *, reason: str, detail: str = "") -> None:
    """Stop one bot and close its run. Safe to call on a bot that is not running.

    Broadcasts the new state so every open panel — not just the tab that asked
    for the stop — reflects it immediately. The auto-stop path already had
    this (``_announce_stop``); a stop this function itself triggers (the
    panel's own button, or one bot being deactivated to activate another)
    deserves the same live sync rather than waiting for a reload.
    """
    async with _LOCK:
        task = _TASKS.pop(bot_id, None)
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await _close_run(bot_id, reason=reason, detail=detail)
    await _broadcast("bot_state", {"bot_id": bot_id, "state": BotState.STOPPED})


async def stop_all(*, reason: str = StopReason.HALT, detail: str = "") -> list[int]:
    """Stop **every** running bot. Q22 calls this the most important of the eight.

    A halt that flattens positions while a bot is still evaluating is a halt that
    re-enters ninety seconds later, which is not a halt. Called from
    ``killswitch.set_stop_all(True)`` and from the panel's flatten path.
    """
    ids = list(running_ids())
    for bot_id in ids:
        await stop(bot_id, reason=reason, detail=detail)
    if ids:
        system_log(
            "WARNING",
            "BOT",
            f"stopped {len(ids)} running bot(s): {detail or reason}",
            source="apps.bots.supervisor",
            context={"bot_ids": ids, "reason": reason},
        )
    return ids


def stop_all_sync(*, reason: str = StopReason.HALT, detail: str = "") -> list[int]:
    """Stop every running bot from synchronous code, database-first.

    The halt is flipped from a DRF view on a worker thread, where there is no
    event loop to await a task cancellation on — and the *authority* on whether
    a bot may trade is ``Bot.state`` in the database, not a live task. Writing
    the state is therefore the halt; cancelling the tasks is cleanup that
    happens on the next loop tick, and the bar loop re-reads ``Bot.state`` every
    bar precisely so a stop taken this way lands immediately.
    """
    ids = list(
        Bot.objects.filter(state__in=[BotState.PAPER, BotState.LIVE]).values_list("id", flat=True)
    )
    if not ids:
        return []
    BotRun.objects.filter(bot_id__in=ids, stopped_at__isnull=True).update(
        stopped_at=timezone.now(), stop_reason=reason, stop_detail=detail[:2000]
    )
    Bot.objects.filter(id__in=ids).update(state=BotState.STOPPED, dry_run=True)
    system_log(
        "WARNING",
        "BOT",
        f"stopped {len(ids)} running bot(s): {detail or reason}",
        source="apps.bots.supervisor",
        error_code=reason,
        context={"bot_ids": ids, "reason": reason},
    )
    for bot_id in ids:
        task = _TASKS.pop(bot_id, None)
        if task is not None and not task.done():
            task.cancel()
    return ids


async def resume_all() -> list[int]:
    """On process start, resume the one bot whose state says it should be running.

    Only one at a time may be active (the panel enforces this on every
    ``start`` — see ``bots.views.start_bot``), but a restart still re-reads
    ``Bot.state`` rather than trusting it: if more than one row is somehow
    left ``paper``/``live`` — data from before this rule existed, or a race —
    the most recently started one wins and the rest are stopped outright,
    never resumed, so a crash can never silently bring two bots back at once.

    The survivor's first act is warm-up and reconciliation, never trading —
    see ``_supervise``.
    """
    bots = await sync_to_async(_bots_to_resume)()
    if len(bots) > 1:
        survivor, *extra = bots
        await sync_to_async(_stop_extra_at_rest)(extra)
        bots = [survivor]
    for bot in bots:
        await start(bot)
    return [bot.id for bot in bots]


async def shutdown() -> None:
    """Cancel every task without writing a stop reason — this is a deploy, not a fault.

    The runs stay open on purpose: the Phase 7 gate asks for "14 days continuous"
    and "≥3 restarts survived", and a deploy that closed the run would make the
    first unmeetable while the second was being measured.
    """
    tasks = list(_TASKS.values())
    _TASKS.clear()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# --- the loop ---------------------------------------------------------------


async def _supervise(bot_id: int, run_id: int) -> None:
    """One bot's whole life. Every exception ends here and nowhere else."""
    try:
        await _run_bot(bot_id, run_id)
    except asyncio.CancelledError:
        raise
    except _AutoStop as stop_signal:
        await _close_run(bot_id, reason=stop_signal.code, detail=stop_signal.detail)
        await _announce_stop(bot_id, stop_signal.code, stop_signal.detail)
    except recovery_module.StateDisagreement as exc:
        # Q25: retried once already inside `recovery`. A second disagreement is
        # not a race, it is a state nobody understands, and auto-correcting one
        # of those is how a recovery becomes a liquidation.
        await _close_run(bot_id, reason=StopReason.STATE_DISAGREEMENT, detail=str(exc))
        await _announce_stop(bot_id, StopReason.STATE_DISAGREEMENT, str(exc))
    except FeedGap as gap:
        # Q25, and not configurable: any gap, the first one. Skipping it would
        # leave the strategy's state machine describing a market that did not
        # happen, and a strategy wrong about the past is wrong about the
        # position it thinks it holds now.
        await sync_to_async(_count_gap)(run_id)
        await _close_run(bot_id, reason=StopReason.FEED_GAP, detail=str(gap))
        await _announce_stop(bot_id, StopReason.FEED_GAP, str(gap))
    except Exception as exc:  # noqa: BLE001 - one bot must never take another with it
        logger.exception("bot %s died", bot_id)
        await _close_run(bot_id, reason=StopReason.SCRIPT_ERROR, detail=str(exc))
        await _announce_stop(bot_id, StopReason.SCRIPT_ERROR, str(exc))
    finally:
        _TASKS.pop(bot_id, None)


class _AutoStop(Exception):
    """A Q25 trigger fired. Carries the reason code the run is closed with."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


async def _run_bot(bot_id: int, run_id: int) -> None:
    bot = await sync_to_async(_load_bot)(bot_id)
    run = await sync_to_async(_load_run)(run_id)
    if bot is None or run is None:
        return

    result = await sync_to_async(_validated)(bot)
    if not result.ok:
        raise _AutoStop(
            StopReason.SCRIPT_ERROR,
            "; ".join(str(e) for e in result.errors),
        )

    runtime = Runtime(
        result.program,
        symbol=bot.symbol,
        inputs=bot.input_values or {},
        limits=await sync_to_async(limits)(),
        symbol_info=await sync_to_async(_symbol_info)(bot),
        timeframe=TimeframeInfo.for_interval(bot.interval),
    )
    feed = BarFeed(symbol=bot.symbol, interval=bot.interval, market=MarketType(bot.market))
    gate = RiskGate(bot, run)

    # --- refuse to start rather than start wrong ---------------------------
    try:
        await feed.check_clock()
        lookback = max(20, result.ta_call_sites * 10)
        warmup = await feed.warmup(lookback=lookback)
    except (ClockSkew, NotEnoughHistory) as exc:
        raise _AutoStop(StopReason.FEED_GAP, str(exc)) from exc

    for bar in warmup:
        # Warm-up converges indicators; every intent it produces is discarded.
        runtime.run_bar(bar, ishistory=True)

    await sync_to_async(_record_warmup)(run, len(warmup), feed.transport)
    system_log(
        "INFO",
        "BOT",
        f"bot {bot.name} warmed up on {len(warmup)} bars via {feed.source or 'archive'}",
        source="apps.bots.supervisor",
        context={"bot_id": bot.id, "run_id": run.id, "bars": len(warmup)},
    )
    await _broadcast("bot_state", {"bot_id": bot.id, "state": bot.state, "run_id": run.id})

    # --- recovery before anything is routed --------------------------------
    await recovery_module.note_unplanned_restart(run)
    await recovery_module.reconcile_run(bot, run)

    # --- the bar loop ------------------------------------------------------
    previous_row: dict | None = None
    async for feed_bar in feed:
        bot = await sync_to_async(_load_bot)(bot_id) or bot
        if bot.state not in (BotState.PAPER, BotState.LIVE):
            raise _AutoStop(StopReason.MANUAL, f"bot moved to {bot.state}")

        run = await sync_to_async(_load_run)(run_id) or run
        gate.bot, gate.run = bot, run

        triggers = await gate.check_triggers()
        if triggers.stop:
            raise _AutoStop(triggers.code, triggers.reason)

        before = await gate.before_bar(bar_time=feed_bar.bar.time)

        # The exchange decides what is open, and the script has to be told
        # *before* it evaluates. An intent is "what should be true after this
        # bar", so it starts from what is actually held; a runtime that was
        # never told anything starts every bar flat, which turns the first
        # quiet bar after an entry into an instruction to close it, and makes
        # `strategy.position_size` read zero live and the real sign in a
        # backtest — a divergence in the one place this design says there is
        # none. The backtest has always done this (`_Engine.step`); this side
        # did not.
        if before.allowed:
            await _reconcile()
        held = await translate.read_held(run)
        equity, performance = await sync_to_async(_run_state)(run)
        runtime.sync_position(
            size_sign=0 if held.flat else (1 if held.side is Side.LONG else -1),
            avg_price=held.avg_price,
            equity=equity,
            opentrades=0 if held.flat else 1,
            performance=performance,
            # What survived the scale-outs so far (Q33), for the same reason the
            # side is passed: a runtime that is not told re-derives it from its
            # own memory, and the next TP1 would be taken off a position that
            # has already been cut.
            fraction=held.fraction,
        )

        try:
            outcome = runtime.run_bar(feed_bar.bar, enforce_budget=True)
        except PineRuntimeError as exc:
            raise _AutoStop(StopReason.SCRIPT_ERROR, str(exc)) from exc
        except PineError as exc:
            raise _AutoStop(StopReason.SCRIPT_ERROR, str(exc)) from exc

        intent = outcome.intent
        previous_row = await sync_to_async(_persist_bar)(
            run, feed_bar, outcome, previous_row
        )
        await _broadcast(
            "bot_bar",
            {
                "bot_id": bot.id,
                "run_id": run.id,
                "bar": feed_bar.bar.as_dict(),
                "transport": feed_bar.transport,
                "source": feed_bar.source,
                "repaired": feed_bar.repaired,
            },
        )
        await _broadcast(
            "bot_intent", {"bot_id": bot.id, "run_id": run.id, "intent": intent.as_dict()}
        )

        if not before.allowed:
            # Paused (the halt, or outside this bot's window). The bar was still
            # evaluated — an indicator that skips bars is a different indicator —
            # and nothing was routed.
            continue

        actions = translate.plan(
            intent=intent, held=held, default_sl=bot.sl_pct, default_tp=bot.tp_pct
        )
        if not actions:
            continue

        for action in actions:
            decision = await gate.check_action(action, bar_close=feed_bar.bar.close)
            if decision.stop:
                raise _AutoStop(decision.code, decision.reason)
            if not decision.allowed:
                actions = []
                break

        if not actions:
            continue

        if bot.dry_run:
            # Phase 7's shadow mode, and it costs one branch. Everything above
            # this line ran for real; only the routing did not.
            await sync_to_async(_record_shadow)(run, feed_bar.bar.time, actions, intent)
            await _broadcast(
                "bot_action",
                {
                    "bot_id": bot.id,
                    "run_id": run.id,
                    "dry_run": True,
                    "actions": [a.as_dict() for a in actions],
                },
            )
            continue

        outcomes = await translate.dispatch(
            bot=bot, run=run, bar_time=feed_bar.bar.time, actions=actions
        )
        await sync_to_async(_record_outcomes)(run, outcomes)
        await _broadcast(
            "bot_action",
            {"bot_id": bot.id, "run_id": run.id, "dry_run": False, "actions": outcomes},
        )


# --- the pieces that touch the database -------------------------------------


def _bots_to_resume() -> list[Bot]:
    # Most recently started/updated first — see resume_all()'s tie-break.
    return list(
        Bot.objects.filter(state__in=[BotState.PAPER, BotState.LIVE]).order_by("-updated_at")
    )


def _stop_extra_at_rest(bots: list[Bot]) -> None:
    """Mark bots stopped without going through the running-task machinery.

    Called only at process start, before any of these bots has a task — there
    is nothing to cancel, only a database row describing a state the panel's
    own one-at-a-time rule no longer allows to resume.
    """
    ids = [bot.id for bot in bots]
    if not ids:
        return
    BotRun.objects.filter(bot_id__in=ids, stopped_at__isnull=True).update(
        stopped_at=timezone.now(),
        stop_reason=StopReason.MANUAL,
        stop_detail="not resumed — only one bot may run at a time",
    )
    Bot.objects.filter(id__in=ids).update(state=BotState.STOPPED, dry_run=True)


def _load_bot(bot_id: int) -> Bot | None:
    return Bot.objects.filter(id=bot_id).select_related("strategy_version").first()


def _load_run(run_id: int) -> BotRun | None:
    return BotRun.objects.filter(id=run_id).select_related("bot").first()


def _validated(bot: Bot):
    from apps.bots.config import limits as bot_limits

    return validate(bot.strategy_version.source, limits=bot_limits())


@sync_to_async
def _open_run(bot: Bot) -> BotRun:
    """The bot's open run, or a new one.

    Resuming into the *same* run across a process restart is what lets the
    Phase 7 gate ask for fourteen continuous days and three survived restarts
    from the same row.
    """
    run = BotRun.objects.filter(bot=bot, stopped_at__isnull=True).order_by("-started_at").first()
    if run is not None:
        run.recoveries += 1
        run.save(update_fields=["recoveries"])
        return run
    return BotRun.objects.create(bot=bot)


@sync_to_async
def _close_run(bot_id: int, *, reason: str, detail: str) -> None:
    run = (
        BotRun.objects.filter(bot_id=bot_id, stopped_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if run is not None:
        run.stopped_at = timezone.now()
        run.stop_reason = reason
        run.stop_detail = detail[:2000]
        run.save(update_fields=["stopped_at", "stop_reason", "stop_detail"])
    Bot.objects.filter(id=bot_id).update(state=BotState.STOPPED, dry_run=True)


def _record_warmup(run: BotRun, bars: int, transport: str) -> None:
    run.warmup_bars = bars
    run.feed_source = transport
    run.save(update_fields=["warmup_bars", "feed_source"])


def _persist_bar(run: BotRun, feed_bar, outcome, previous: dict | None) -> dict:
    """Store the evaluated bar, subject to Q26, and advance the run's counters."""
    intent = outcome.intent.as_dict()
    plots = intent.get("plots", {})
    changed = retention.is_change(previous, intent, plots)
    bar = feed_bar.bar

    if retention.keeps_every_bar(run.bot.interval) or changed:
        BotBar.objects.update_or_create(
            run=run,
            bar_time=bar.time,
            defaults={
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "plots": plots,
                "intent": intent,
                "evaluation_ms": outcome.elapsed_ms,
                "changed": changed,
            },
        )
    run.last_bar_time = bar.time
    run.bars_evaluated += 1
    if feed_bar.repaired:
        run.feed_gaps_repaired += 1
    run.save(update_fields=["last_bar_time", "bars_evaluated", "feed_gaps_repaired"])
    retention.trim(run)
    return {"intent": intent, "plots": plots}


def _record_shadow(run: BotRun, bar_time: int, actions, intent) -> None:
    """A dry-run bot's would-have-been, written down like any other action.

    Recorded rather than only logged because Phase 7's divergence check compares
    these against a backtest over the same bars, and a comparison needs rows.
    """
    for ordinal, action in enumerate(actions):
        BotAction.objects.get_or_create(
            idempotency_key=translate.idempotency_key(run.id, bar_time, "shadow", ordinal),
            defaults={
                "run": run,
                "bar_time": bar_time,
                "action_type": "shadow",
                "reason": action.reason[:200],
                "intent": {**action.as_dict(), "would_be": action.type},
                "ok": True,
                "settled_at": timezone.now(),
            },
        )


def _record_outcomes(run: BotRun, outcomes: list[dict]) -> None:
    """Update the run's own counters from what came back.

    ``consecutive_losses`` and ``peak_equity`` live on the run because Q25's
    drawdown trigger is measured from the bot's *own* peak, not the account's:
    a bot that gave back its own gains has a problem even while the book is up.
    """
    from apps.trading.models import Trade, TradeStatus

    closed = [o for o in outcomes if o.get("action", {}).get("type") == "close"]
    for outcome in closed:
        trade_id = outcome.get("trade_id")
        if not trade_id:
            continue
        trade = Trade.objects.filter(id=trade_id, status=TradeStatus.CLOSED).first()
        if trade is None:
            continue
        pnl = sum((leg.pnl or Decimal("0")) for leg in trade.legs.all())
        run.consecutive_losses = run.consecutive_losses + 1 if pnl <= 0 else 0
    equity = _current_equity()
    if equity is not None and (run.peak_equity is None or equity > run.peak_equity):
        run.peak_equity = equity
    run.save(update_fields=["consecutive_losses", "peak_equity"])


def _current_equity() -> Decimal | None:
    from apps.accounts.models import ConnectedAccount

    values = [
        Decimal(str(v))
        for v in ConnectedAccount.objects.filter(active=True).values_list(
            "last_balance", flat=True
        )
        if v is not None
    ]
    return sum(values, Decimal("0")) if values else None


def _symbol_info(bot: Bot) -> SymbolInfo:
    """The instrument, from the exchange's own listing where there is one.

    ``syminfo.mintick`` is the field with teeth — ``math.round_to_mintick`` and
    any level a script rounds itself go through it — so it comes from
    ``ExchangeSymbol``, which is downloaded at connect time, rather than from a
    default that would be quietly wrong on a pair priced in eight decimals.
    """
    from apps.trading.models import ExchangeSymbol

    listing = (
        ExchangeSymbol.objects.filter(symbol=bot.symbol, market=bot.market, active=True)
        .exclude(price_tick=None)
        # The finest tick any connected venue quotes. A stop rounded to a
        # coarser grid than some account's exchange uses would be rejected
        # there and nowhere else, which is the one failure mode §4's account
        # isolation cannot absorb.
        .order_by("price_tick")
        .first()
    )
    return SymbolInfo.for_symbol(
        bot.symbol,
        market=bot.market,
        mintick=listing.price_tick if listing is not None else None,
    )


def _run_state(run: BotRun) -> tuple[Decimal, dict]:
    """``(equity, performance)`` — everything the script reads about the account.

    One call because the two share a query: the percentages below are against
    equity, and reading it twice a bar for two callers is a query for nothing.
    """
    equity = _current_equity()
    return (equity or ZERO), _performance(run, equity)


def _performance(run: BotRun, capital: Decimal | None) -> dict:
    """``strategy.closedtrades`` and the rest, for **this run's own** trades.

    The live counterpart of ``backtest._Engine._performance``, and deliberately
    the same shape: a script's dashboard has to read the same names in both, or
    a strategy that guards on ``strategy.closedtrades > 5`` behaves differently
    the day it goes live.

    "This run's" is the scope on purpose. The account has a history of manual
    trades and of earlier bots, and none of it is what this script's own
    counters mean — ``apps.accounts.report`` is where the account's whole story
    lives.
    """
    from apps.trading.models import Trade, TradeStatus

    trades = list(
        Trade.objects.filter(bot_run=run, status=TradeStatus.CLOSED).prefetch_related("legs")
    )
    realised = [
        sum((leg.pnl for leg in trade.legs.all() if leg.pnl is not None), ZERO)
        for trade in trades
    ]
    wins = [value for value in realised if value > ZERO]
    losses = [value for value in realised if value < ZERO]
    net = sum(realised, ZERO)
    # What the accounts held before this run traded — equity now, less what the
    # run made. Unknown when no account reports a balance, and the percentages
    # are then zero rather than a ratio against a made-up denominator: a
    # dashboard reading "+400%" because the base was 1 is worse than one
    # reading nothing.
    base = (capital - net) if capital is not None and capital - net > ZERO else None
    percent = (lambda value: value / base * Decimal(100)) if base else (lambda _: ZERO)
    return {
        "closedtrades": Decimal(len(trades)),
        "wintrades": Decimal(len(wins)),
        "losstrades": Decimal(len(losses)),
        "eventrades": Decimal(len(trades) - len(wins) - len(losses)),
        "initial_capital": base if base is not None else ZERO,
        "netprofit": net,
        "netprofit_percent": percent(net),
        "grossprofit": sum(wins, ZERO),
        "grossprofit_percent": percent(sum(wins, ZERO)),
        "grossloss": -sum(losses, ZERO),
        "grossloss_percent": percent(-sum(losses, ZERO)),
        "avg_trade": (net / Decimal(len(trades))) if trades else ZERO,
        "account_currency": "USDT",
    }


async def _reconcile() -> None:
    """Make the record match the exchange before anything is diffed against it."""
    from apps.trading import possync, services

    with contextlib.suppress(Exception):
        await services.reconcile_open_trade()
    with contextlib.suppress(Exception):
        await possync.sync_positions()


async def _announce_stop(bot_id: int, reason: str, detail: str) -> None:
    system_log(
        "ERROR",
        "BOT",
        f"bot {bot_id} stopped: {reason} — {detail}",
        source="apps.bots.supervisor",
        error_code=reason,
        context={"bot_id": bot_id},
    )
    await _broadcast("bot_stopped", {"bot_id": bot_id, "reason": reason, "detail": detail})


def _count_gap(run_id: int) -> None:
    """Record the gap on the run. The Phase 7 gate reads these counters."""
    run = BotRun.objects.filter(id=run_id).first()
    if run is not None:
        run.feed_gaps += 1
        run.save(update_fields=["feed_gaps"])
