"""The operator's own hand on a running bot — Q41.

TradingView and the bot can disagree. The bot was stopped when the signal
fired, the feed was repairing a gap, a bar arrived late, the script's condition
was one tick off. The chart says long and the platform is flat, and by the time
anybody notices, waiting for the *next* signal means sitting out the trade the
strategy is in.

So this is the door for "do it anyway". Two buttons: open what the chart shows,
or close what the platform is holding. And the rule the whole module exists to
keep is that pressing one **does not** put the bot and the operator on separate
tracks:

  **There is no second order path.** ``apps.bots.translate`` opens with that
  rule and ``apps.signals.service`` repeats it. A press here becomes a
  ``StrategyIntent`` — the same object a Pine bar produces — and goes through
  the same ``translate.plan``, the same ``RiskGate``, the same
  ``translate.dispatch``, the same ``route_*``, the same fan-out, the same
  reconciliation, the same history. Everything below ``plan()`` cannot tell a
  press from a bar.

  **A manual entry is the bot's position from the next bar on.** The trade is
  stamped with the run (``translate._link_trade``), so ``read_held`` finds it,
  ``sync_position`` tells the runtime about it before the next bar is
  evaluated, and the script's own exit — a ``strategy.close``, a reversal, a
  level it computed — closes it exactly as if the bot had opened it. Nothing
  here teaches the strategy anything: it is told what is held, which is what it
  is told on every other bar.

  **A manual exit is not an invitation to re-enter.** The runtime starts each
  bar from the position the exchange says is there, so after a manual close it
  starts flat and only the script's own order call can move it again. That is
  most of the answer — and the gap it leaves is the entry condition that is
  *still true*: a strategy whose signal is a state rather than a crossing asks
  to enter on every bar it holds, so the position the operator just took off
  would be back within one bar. The guard at the bottom of this file closes
  that gap by waiting for the script to **stop asking** and then ask again,
  which is what "the next valid entry signal" means when the signal is a
  condition rather than an event.

What this module deliberately does not do is bypass anything. The halt still
refuses an entry, the risk gate still measures it, an account that has not
opted into bot trading is still not asked, and sizing is still §5. An override
of the *strategy* is not an override of the platform.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from decimal import Decimal

from asgiref.sync import sync_to_async

from apps.bots import translate
from apps.bots.models import ActionType, Bot, BotRun, BotState
from apps.bots.riskgate import RiskGate
from apps.logging.utils import system_log
from apps.pine.intent import Side, StrategyIntent

logger = logging.getLogger(__name__)

#: The same "no bar to compare against" the webhook path passes. The drift
#: check exists to catch a bar feed that has stopped moving or a symbol mapped
#: to the wrong instrument — and a feed that has stopped moving is one of the
#: reasons somebody is standing at this tab in the first place. Refusing their
#: press because the bot's own feed is stale would be the check firing at the
#: person trying to work around it. Every other gate check runs unchanged.
NO_BAR = Decimal("0")


def _scope(now: float | None = None) -> str:
    """The idempotency scope: the second the press arrived in.

    Two clicks in the same second produce the same
    ``BotAction.idempotency_key``, so the second is recorded as already
    dispatched rather than sent — which is exactly what a double-click should
    do to a market order. The *bar* keeps its real value in the key, so a
    manual action still lands on the chart where it happened.
    """
    return f"man{int(now if now is not None else time.time())}"


OPEN_LONG = "open_long"
OPEN_SHORT = "open_short"
CLOSE = "close"
VERBS = (OPEN_LONG, OPEN_SHORT, CLOSE)

_SIDE_OF = {OPEN_LONG: Side.LONG, OPEN_SHORT: Side.SHORT, CLOSE: None}


@dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one press. Shaped like ``signals.service.Outcome``."""

    ok: bool
    code: str
    detail: str = ""
    status: int = 200
    actions: list[dict] = field(default_factory=list)
    run_id: int | None = None
    trade_id: int | None = None


class Refused(Exception):
    """A press that was not routed, with the reason the panel shows."""

    def __init__(self, code: str, detail: str, status: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def open_run(bot: Bot) -> BotRun | None:
    return BotRun.objects.filter(bot=bot, stopped_at=None).order_by("-started_at").first()


def latest_run(bot: Bot) -> BotRun | None:
    return bot.runs.order_by("-started_at").first()


@sync_to_async
def _load(bot_id: int) -> tuple[Bot | None, BotRun | None, BotRun | None]:
    bot = Bot.objects.select_related("strategy_version").filter(id=bot_id).first()
    if bot is None:
        return None, None, None
    return bot, open_run(bot), latest_run(bot)


# --- the press --------------------------------------------------------------


async def act(*, bot_id: int, verb: str, actor: str = "") -> Outcome:
    """Route one manual instruction for ``bot_id``, or say why it was not.

    ``verb`` is one of ``VERBS``. Raises ``Refused`` for everything the
    operator can act on — a stopped bot, a halt, a gate that says no — and
    returns an ``Outcome`` for everything that reached the order path,
    including the cases where the right answer was to send nothing.
    """
    if verb not in VERBS:
        raise Refused("unknown_verb", f"{verb!r} is not one of {', '.join(VERBS)}", status=400)

    bot, run, last = await _load(bot_id)
    if bot is None:
        raise Refused("no_bot", "no such bot", status=404)

    side = _SIDE_OF[verb]
    running = bot.state in (BotState.PAPER, BotState.LIVE) and run is not None

    if side is not None and not running:
        # An entry needs somebody to manage it afterwards, and that somebody is
        # the run. Opening into a stopped bot would produce a position no
        # strategy is watching and no later run would even find — trades are
        # stamped with the run that made them.
        raise Refused(
            "bot_not_running",
            f"“{bot.name}” is {bot.state}. Start it before opening a position from here — "
            "an entry with no run behind it is a position the strategy will never close.",
        )

    # A close is allowed on the run that holds the trade, running or not. A bot
    # that stopped itself at 03:00 while holding is the case this tab is most
    # needed for, and refusing to flatten it would be the panel protecting a
    # rule at the operator's expense.
    run = run or last
    if run is None:
        raise Refused("no_run", f"“{bot.name}” has never run", status=409)

    gate = RiskGate(bot, run)
    if side is not None:
        before = await gate.before_bar(bar_time=int(time.time()))
        if not before.allowed:
            raise Refused(before.code or "paused", before.reason)

    # The exchange decides what is held, not this database — re-read before
    # diffing against it, exactly as the supervisor does on every bar and for
    # the same reason.
    from apps.trading.services import reconcile_open_trade

    await reconcile_open_trade()
    held = await translate.read_held(run)

    if side is None and held.flat:
        return Outcome(
            ok=True,
            code="already_flat",
            detail="this bot is not holding anything — there is nothing to close",
            run_id=run.id,
        )

    bar_time = run.last_bar_time or int(time.time())
    intent = StrategyIntent(
        bar_time=bar_time,
        symbol=bot.symbol,
        desired_side=side,
        # Deliberately no percentages: leaving them blank is what makes
        # ``plan()`` fall back to the bot's own configured pair, so a manual
        # entry is protected by the numbers every other entry of this bot uses
        # rather than by a second set typed into a dialog.
        reason=_reason(verb, actor),
        entry_signal=side is not None,
    )
    actions = translate.plan(
        intent=intent,
        held=held,
        default_sl=bot.sl_pct,
        default_tp=bot.tp_pct,
        policy=bot.exit_policy,
        safety_net=bot.safety_net_pct,
    )
    if not actions:
        return Outcome(
            ok=True,
            code="already_there",
            detail="the position already matches this instruction — nothing was sent",
            run_id=run.id,
        )

    actions = [replace(action, origin="manual", actor=actor) for action in actions]

    for action in actions:
        decision = await gate.check_action(action, bar_close=NO_BAR)
        if not decision.allowed:
            # Reported, never acted on as a stop. The gate's stop flag means
            # "this bot should not be trading"; a person pressing a button has
            # already decided otherwise about this one order, and stopping the
            # bot out from under them would be a second consequence they did
            # not ask for.
            raise Refused(decision.code or "risk_gate", decision.reason)

    if bot.dry_run:
        # Paper. Everything above this line ran for real; only the routing did
        # not — the same single branch the supervisor's shadow mode is.
        await sync_to_async(_record_shadow)(run, bar_time, actions, intent)
        await _note(bot, run, verb, actor, routed=False)
        return Outcome(
            ok=True,
            code="paper",
            detail=f"“{bot.name}” is in paper — recorded, routed nowhere",
            actions=[action.as_dict() for action in actions],
            run_id=run.id,
        )

    outcomes = await translate.dispatch(
        bot=bot, run=run, bar_time=bar_time, actions=actions, scope=_scope()
    )
    await sync_to_async(_record_outcomes)(run, outcomes)
    # What the press means for the bars that follow it. Keyed on what was
    # *held* when the plan was made rather than on what the trade row says
    # afterwards: a close that left one leg behind leaves the trade open, and
    # the side the operator took off is still the side they took off.
    await sync_to_async(remember)(
        run,
        verb=verb,
        side=held.side.value if held.side else "",
        bar_time=bar_time,
    )
    await _note(bot, run, verb, actor, routed=True)
    trade_id = next(
        (out.get("trade_id") for out in reversed(outcomes) if out.get("trade_id")), None
    )
    return Outcome(
        ok=any(out.get("ok") for out in outcomes),
        code="routed",
        actions=outcomes,
        run_id=run.id,
        trade_id=trade_id,
    )


def _reason(verb: str, actor: str) -> str:
    who = f" by {actor}" if actor else ""
    if verb == CLOSE:
        return f"closed by hand{who}"
    return f"opened by hand{who}"


def _record_shadow(run: BotRun, bar_time: int, actions, intent) -> None:
    """Paper's would-have-been, written through the bot app's own recorder."""
    from apps.bots.supervisor import _record_shadow as record

    record(run, bar_time, actions, intent, _scope())


def _record_outcomes(run: BotRun, outcomes: list[dict]) -> None:
    """The run's own counters, updated through the bot app's own recorder."""
    from apps.bots.supervisor import _record_outcomes as record

    record(run, outcomes)


async def _note(bot: Bot, run: BotRun, verb: str, actor: str, *, routed: bool) -> None:
    """One log row per press. The trade itself is already announced by the
    order path; this is the fact that a *person* is the reason it happened."""
    system_log(
        "WARNING",
        "BOT",
        f"bot {bot.name}: {verb.replace('_', ' ')} by hand"
        + (f" ({actor})" if actor else "")
        + ("" if routed else " — paper, routed nowhere"),
        source="apps.bots.intervene",
        error_code="bot_intervention",
        context={
            "bot": bot.name,
            "bot_id": bot.id,
            "run_id": run.id,
            "actor": actor,
            "reason": verb,
            "mode": bot.state,
            "symbol": bot.symbol,
            "interval": bot.interval,
        },
    )


# --- the re-entry guard -----------------------------------------------------
#
# What the operator means by "do not reopen it", written as a state machine
# over the bars that follow the press.
#
# The naive reading — "ignore the next entry" — is wrong in both directions. A
# strategy whose entry condition is a *state* (`emaFast > emaSlow`) calls
# ``strategy.entry`` on every bar the state holds, so ignoring one bar
# re-enters on the next; a strategy that signals on a *crossing* asks once and
# may not ask again for days, so ignoring its next ask would skip a trade the
# operator wanted.
#
# What both have in common is the transition. The entry the operator overrode
# is the one that is *still being asked for*; the next **valid** one is the ask
# that arrives after the script has stopped asking. So:
#
#     closed by hand  ──▶  HOLDING ──(script still asking)──▶ HOLDING
#                              │
#                     (script quiet on a later bar)
#                              ▼
#                           ARMED ──(script asks again)──▶ released, routed
#
# ``manual_flat_side`` is the side being held; ``manual_flat_bar`` is the last
# bar it was still being asked for, and ``None`` there means ARMED. Two fields,
# no timer, and nothing that has to be re-derived from the script's source.

#: The guard's four answers for one bar.
HOLD = "hold"
ARM = "arm"
CLEAR = "clear"
PASS = "pass"


def remember(run: BotRun, *, verb: str, side: str, bar_time: int) -> None:
    """Record what the press means for the bars that follow it.

    A manual **close** starts the guard HOLDING ``side``. A manual **open**
    clears it outright: the operator has just put a position back on, so there
    is nothing left to protect from being re-entered.
    """
    if verb == CLOSE:
        run.manual_flat_side = side
        run.manual_flat_bar = bar_time
    else:
        run.manual_flat_side = ""
        run.manual_flat_bar = None
    run.save(update_fields=["manual_flat_side", "manual_flat_bar"])


def clear(run: BotRun) -> None:
    if not run.manual_flat_side and run.manual_flat_bar is None:
        return
    run.manual_flat_side = ""
    run.manual_flat_bar = None
    run.save(update_fields=["manual_flat_side", "manual_flat_bar"])


def decide(
    actions: list[translate.Action],
    *,
    guard_side: str,
    guard_bar: int | None,
    bar_time: int,
) -> str:
    """What this bar does to the guard. Pure — the whole rule is here.

    ``guard_bar is None`` is ARMED. An ``OPEN`` of the guarded side is the
    script asking; anything else — a close, an amend, a scale-out, an entry the
    other way, or nothing at all — is the script not asking for *this* side,
    which is what arms the guard and, for an entry the other way, retires it.
    """
    if not guard_side:
        return PASS

    asking = False
    other_way = False
    for action in actions:
        if action.type != ActionType.OPEN or action.side is None:
            continue
        if action.side.value == guard_side:
            asking = True
        else:
            other_way = True

    if other_way:
        # A new position, the other way round. The side the operator took off
        # is no longer what this bot is doing, so the guard has nothing left to
        # protect and holding it would ambush a later reversal back.
        return CLEAR
    if asking:
        # Still the same ask the press overrode — unless the script has been
        # quiet since, which is what ARMED records. An armed guard releases
        # *and retires*: it exists to stop one re-entry, and once the strategy
        # has signalled a new one there is nothing left for it to do.
        return CLEAR if guard_bar is None else HOLD
    # The script is not asking for this side on this bar. That is the
    # transition: from here, the next ask is a new signal. The bar the press
    # landed on is excluded, because that bar is the one being overridden.
    if guard_bar is not None and bar_time > guard_bar:
        return ARM
    return PASS


def resolve(run: BotRun, actions: list[translate.Action], intent: StrategyIntent) -> bool:
    """Apply ``decide`` to one bar and persist what it did. Returns "held off".

    Called on **every** evaluated bar, including the ones that planned nothing:
    a bar with no plan is exactly how the script says it has stopped asking,
    and a guard that only looked at bars with actions on them could never arm.
    """
    verdict = decide(
        actions,
        guard_side=run.manual_flat_side,
        guard_bar=run.manual_flat_bar,
        bar_time=intent.bar_time,
    )
    if verdict == HOLD:
        # Renew, so "the last bar it was still being asked for" stays true and
        # the arming test keeps measuring from the right place.
        if run.manual_flat_bar != intent.bar_time:
            run.manual_flat_bar = intent.bar_time
            run.save(update_fields=["manual_flat_bar"])
        return True
    if verdict == ARM:
        run.manual_flat_bar = None
        run.save(update_fields=["manual_flat_bar"])
    elif verdict == CLEAR:
        clear(run)
    return False
