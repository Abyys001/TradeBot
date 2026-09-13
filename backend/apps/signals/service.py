"""Where an external signal joins the order path that already exists.

This module is the webhook's whole execution story, and it is short on purpose.
``apps.bots.translate`` opens with a rule — *if a diff here ever adds a second
order path it is wrong regardless of what it does* — and that rule binds this
file at least as hard: the sender is outside the platform, so a private route
for it would be a set of rules about partner capital that nobody reviewing the
bot path would ever see.

So there is no private route. A delivery becomes a ``StrategyIntent`` — the
same object a Pine bar produces — and goes through the same ``translate.plan``,
the same ``RiskGate``, the same ``translate.dispatch``, the same ``route_*``,
the same fan-out, the same reconciliation, the same history. Everything below
``plan()`` cannot tell the two apart, and that is the point.

**The exit is the reason this exists.** ``EXIT_BUY`` becomes
``desired_side = None``, which ``plan()`` turns into a ``CLOSE`` against
whatever the exchange says is held. Nothing on that path reads PnL, consults a
percentage, or checks whether a target was reached — a strategy exit closes the
position because the strategy said so, in profit or in loss, and it is the only
thing that needed to be true for Q37 to work.

**Four guards, before any of that.** The bot must be running, the halt must be
off, the verb must match what is actually held, and the delivery must not be
one this platform has already acted on. The third is the one worth naming: an
``EXIT_BUY`` that arrives while the bot is *short* is not an instruction to
flatten the short. The verb names the side it acts on, and a stale duplicate
from a retrying alert system is exactly how that situation arises — so it is
recorded as a no-op with a reason, never routed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from asgiref.sync import sync_to_async

from apps.bots import translate
from apps.bots.models import Bot, BotRun, BotState
from apps.bots.riskgate import RiskGate
from apps.signals.models import SignalEvent, SignalSource, Verdict
from apps.signals.payload import Signal

logger = logging.getLogger(__name__)

#: Passed as the "bar close" to ``RiskGate.check_action``. Zero disables the
#: bar-versus-ticker drift check by the gate's own contract, which is correct
#: rather than convenient: that check exists to catch a **bar feed** that has
#: stopped moving or a symbol mapped to the wrong instrument, and a webhook bot
#: has no bar feed to be stale. Every other gate check — the account cap, the
#: halt, the trading window, the trade-rate and drawdown auto-stops — runs
#: exactly as it does for a Pine bot.
NO_BAR = Decimal("0")

#: The idempotency scope. Keeps signal-driven actions from ever colliding with
#: a bar-driven one in ``BotAction.idempotency_key``.
SCOPE = "sig"


@dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one delivery. Written onto the ``SignalEvent``."""

    verdict: str
    code: str = ""
    detail: str = ""
    actions: list[dict] | None = None
    run_id: int | None = None

    @property
    def accepted(self) -> bool:
        return self.verdict == Verdict.ACCEPTED

    @property
    def http_status(self) -> int:
        """A no-op and a duplicate are both 200.

        The sender did nothing wrong in either case, and an alert system that
        sees a 4xx will retry — which for a duplicate means retrying the thing
        that was already refused as a retry. Only a refusal the sender can fix
        gets an error status, and ``views`` picks that one.
        """
        return 200


def _open_run(bot: Bot) -> BotRun | None:
    return BotRun.objects.filter(bot=bot, stopped_at=None).order_by("-started_at").first()


@sync_to_async
def _load(source_id: int) -> tuple[SignalSource | None, Bot | None, BotRun | None]:
    source = (
        SignalSource.objects.select_related("bot").filter(id=source_id).first()
    )
    if source is None:
        return None, None, None
    return source, source.bot, _open_run(source.bot)


async def apply(*, source: SignalSource, signal: Signal, event: SignalEvent) -> Outcome:
    """Route one parsed signal, or say why it was not routed.

    ``event`` is already written when this is called — the row is the
    deduplication (its ``(source, signal_id)`` constraint), so it has to exist
    before anything is sent, for the same reason ``BotAction`` is claimed
    before dispatch: the case being defended against is two deliveries in
    flight at once, and at that moment nothing is holding a lock.
    """
    _, bot, run = await _load(source.id)
    if bot is None:
        return Outcome(Verdict.REJECTED, "no_bot", "this source is not bound to a bot")

    if bot.state not in (BotState.PAPER, BotState.LIVE) or run is None:
        return Outcome(
            Verdict.REJECTED,
            "bot_not_running",
            f"bot “{bot.name}” is {bot.state} — start it before sending signals. "
            "A signal is never queued for later: by the time a stopped bot is "
            "restarted, the market it described is gone.",
        )

    gate = RiskGate(bot, run)
    before = await gate.before_bar(bar_time=event.id)
    if not before.allowed:
        return Outcome(Verdict.REJECTED, before.code or "paused", before.reason)

    # The exchange decides what is held, not this database — so re-read before
    # diffing against it, exactly as the supervisor does on every bar.
    from apps.trading.services import reconcile_open_trade

    await reconcile_open_trade()
    held = await translate.read_held(run)

    guard = _verb_against_position(signal, held)
    if guard is not None:
        return Outcome(Verdict.NOOP, guard[0], guard[1], run_id=run.id)

    intent = signal.as_intent(bar_time=event.id)
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
            Verdict.NOOP,
            "already_there",
            "the position already matches this signal — nothing to send",
            run_id=run.id,
        )

    for action in actions:
        decision = await gate.check_action(action, bar_close=NO_BAR)
        if not decision.allowed:
            return Outcome(
                Verdict.REJECTED,
                decision.code or "risk_gate",
                decision.reason,
                run_id=run.id,
            )

    if bot.dry_run:
        # Paper. Everything above this line ran for real; only the routing did
        # not — the same single branch the supervisor's shadow mode is.
        payload = [action.as_dict() for action in actions]
        await sync_to_async(_record_shadow)(run, event.id, actions, intent, SCOPE)
        return Outcome(
            Verdict.ACCEPTED,
            "paper",
            f"bot “{bot.name}” is in paper — recorded, routed nowhere",
            actions=payload,
            run_id=run.id,
        )

    outcomes = await translate.dispatch(
        bot=bot, run=run, bar_time=event.id, actions=actions, scope=SCOPE
    )
    # The same counters a bar-driven action updates. Q25's drawdown and
    # consecutive-loss auto-stops are measured from these, and a bot that only
    # ever traded on signals would otherwise be the one bot they never fire for.
    await sync_to_async(_record_outcomes)(run, outcomes)
    return Outcome(Verdict.ACCEPTED, "routed", "", actions=outcomes, run_id=run.id)


def _verb_against_position(signal: Signal, held: translate.Held) -> tuple[str, str] | None:
    """Refuse an exit that does not describe the position actually held.

    Returns ``(code, detail)`` for a no-op, or ``None`` to carry on.

    An entry verb needs no equivalent check: ``plan()`` already turns "buy
    while long" into no action and "buy while short" into a sequenced reversal,
    both of which are the right answer. Only the exits need a side test,
    because ``desired_side = None`` says *flat* without saying *from what* —
    and honouring an ``EXIT_BUY`` against a short would close a position the
    sender never mentioned.
    """
    if not signal.verb.is_exit:
        return None
    if held.flat:
        return (
            "nothing_open",
            f"{signal.verb.value} arrived with no position open — already flat",
        )
    if held.side is not signal.verb.side:
        return (
            "wrong_side",
            f"{signal.verb.value} names the {signal.verb.side.value} side and this bot "
            f"is {held.side.value} — an exit is not routed against the other side",
        )
    return None


def _record_shadow(run: BotRun, bar_time: int, actions, intent, scope: str) -> None:
    """Paper's would-have-been, written through the bot app's own recorder."""
    from apps.bots.supervisor import _record_shadow as record

    record(run, bar_time, actions, intent, scope)


def _record_outcomes(run: BotRun, outcomes: list[dict]) -> None:
    """The run's own counters, updated through the bot app's own recorder."""
    from apps.bots.supervisor import _record_outcomes as record

    record(run, outcomes)
