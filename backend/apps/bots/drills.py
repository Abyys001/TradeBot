"""Drills: firing the safety machinery on purpose, and recording that it worked.

The promotion gate asks for two things nobody can prove by remembering them —
that the kill switch has been pulled on this bot and that every Q25 auto-stop
has been fired deliberately. Before this module those rows could only be filled
in by hand-editing ``risk_config``, which makes the gate a form rather than a
measurement.

**The halt drill is the real thing, not a simulation.** It engages the §7 halt,
which stops every running bot (Q22), then **force-closes every open trade
through ``route_close_all``** — the same call the panel's Stop-all makes, with
no reference whatsoever to what the strategy thinks should be open. That is the
whole point of the exercise: the way out of a position must not run through the
strategy, because the case it exists for is the strategy being wrong.

Then it puts things back. The halt is released, and the bot is resumed **into
the same run**, which is what a real halt-and-resume does and what keeps the
soak clock honest — the fourteen days are continuous *operation*, and a drill
that reset them to zero would mean no bot could ever satisfy both rows at once.
The resume is counted as an unplanned recovery, because that is exactly what it
is, and the run's ``halt_drills`` goes up by one.

A Q25 drill is narrower and says so: it stops the bot **with that reason code**
and resumes it, which exercises the stop path, the reason plumbing and the
restart for that trigger. It does not fabricate the condition — there is no
honest way to invent three consecutive losses — so what it proves is the
response, and the panel words it that way.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.bots.gate import DRILL_TRIGGERS
from apps.bots.models import Bot, BotRun, BotState

logger = logging.getLogger(__name__)

#: The halt drill's own name in ``Bot.drills_fired``. Not a ``StopReason`` value
#: by accident — ``StopReason.HALT`` is what the run is closed with.
HALT_DRILL = "halt"


class DrillRefused(Exception):
    """The drill cannot be run right now, and the reason is worth showing."""


@dataclass(frozen=True, slots=True)
class DrillResult:
    kind: str
    trades_closed: int
    legs_ok: int
    legs_failed: int
    resumed: bool
    halt_drills: int
    drills_fired: tuple[str, ...]
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "trades_closed": self.trades_closed,
            "legs_ok": self.legs_ok,
            "legs_failed": self.legs_failed,
            "resumed": self.resumed,
            "halt_drills": self.halt_drills,
            "drills_fired": list(self.drills_fired),
            "detail": self.detail,
        }


async def run_halt_drill(bot: Bot, *, actor: str = "") -> DrillResult:
    """Pull the kill switch on this bot for real, flatten, and put it back."""
    from apps.trading import killswitch
    from apps.trading.services import route_close_all

    if bot.state not in (BotState.PAPER, BotState.LIVE):
        raise DrillRefused(
            "a kill-switch drill proves a *running* bot stops — start it into paper first"
        )

    was_live = bot.state == BotState.LIVE
    run = await sync_to_async(_open_run_of)(bot)
    if run is None:
        raise DrillRefused("this bot has no open run to drill")

    reason = f"kill-switch drill by {actor or 'the panel'}"
    try:
        # Engaging the halt is what stops the bot — `set_stop_all` calls
        # `supervisor.stop_all_sync` itself (Q22). Nothing here re-implements it.
        await sync_to_async(killswitch.set_stop_all)(True, actor=actor, reason=reason)

        # And this is the row the drill exists to prove: flattening does not ask
        # the strategy. `route_close_all` works while halted, by design — the
        # halt stops new routing, never the way out of a position.
        closed = await route_close_all()
        trades = len(closed)
        legs_ok = sum(len(result.succeeded) for _, result in closed)
        legs_failed = sum(len(result.failed) for _, result in closed)
    finally:
        # Released even if the close raised. A drill that left the platform
        # halted would be a drill nobody runs twice.
        try:
            await sync_to_async(killswitch.set_stop_all)(
                False, actor=actor, reason="kill-switch drill finished"
            )
        except PermissionError:
            # STOP_ALL is pinned on by the environment. It was already on before
            # the drill, so nothing has been made worse — say so and move on.
            logger.warning("kill-switch drill left the env-pinned halt in place")

    resumed = await _resume_same_run(bot, run, live=was_live)
    counts = await sync_to_async(_record_halt_drill)(bot.id, run.id)
    return DrillResult(
        kind=HALT_DRILL,
        trades_closed=trades,
        legs_ok=legs_ok,
        legs_failed=legs_failed,
        resumed=resumed,
        halt_drills=counts[0],
        drills_fired=counts[1],
        detail=reason,
    )


async def run_trigger_drill(bot: Bot, trigger: str, *, actor: str = "") -> DrillResult:
    """Stop the bot with ``trigger``'s reason code, then resume it."""
    from apps.bots import supervisor

    if trigger not in set(DRILL_TRIGGERS):
        raise DrillRefused(f"{trigger!r} is not one of the Q25 auto-stops")
    if bot.state not in (BotState.PAPER, BotState.LIVE):
        raise DrillRefused("start the bot into paper before firing an auto-stop drill")

    was_live = bot.state == BotState.LIVE
    run = await sync_to_async(_open_run_of)(bot)
    if run is None:
        raise DrillRefused("this bot has no open run to drill")

    await supervisor.stop(
        bot.id,
        reason=trigger,
        detail=f"{trigger} drill fired deliberately by {actor or 'the panel'}",
    )
    resumed = await _resume_same_run(bot, run, live=was_live)
    counts = await sync_to_async(_record_trigger_drill)(bot.id, trigger)
    return DrillResult(
        kind=trigger,
        trades_closed=0,
        legs_ok=0,
        legs_failed=0,
        resumed=resumed,
        halt_drills=counts[0],
        drills_fired=counts[1],
    )


def acknowledge_adapters(bot: Bot, *, actor: str, on: bool) -> dict:
    """The one gate row that cannot be measured from inside (``docs/adapters.md``).

    Kept as a row rather than deleted, and made tickable rather than left as a
    field only a shell can set: the person pressing this has read what it says,
    and *who* pressed it and *when* are recorded alongside the answer. A gate
    that can only be cleared by editing the database is a gate people route
    around.
    """
    config = dict(bot.risk_config or {})
    if on:
        config["adapters_tested_on_testnet"] = True
        config["adapters_acknowledged_by"] = actor[:150]
        config["adapters_acknowledged_at"] = timezone.now().isoformat()
    else:
        for key in (
            "adapters_tested_on_testnet",
            "adapters_acknowledged_by",
            "adapters_acknowledged_at",
        ):
            config.pop(key, None)
    bot.risk_config = config
    bot.save(update_fields=["risk_config", "updated_at"])
    return config


# --- the database half ------------------------------------------------------


def _open_run_of(bot: Bot) -> BotRun | None:
    return BotRun.objects.filter(bot=bot, stopped_at__isnull=True).order_by("-started_at").first()


async def _resume_same_run(bot: Bot, run: BotRun, *, live: bool) -> bool:
    """Reopen the run the drill closed and start the task back on it.

    Reopening rather than starting a fresh run is the honest reading: the bot
    was interrupted and came back, which is what ``recoveries`` counts and what
    "continuous runtime" means for a system that is expected to survive
    restarts. A new run would say the soak began again, which is not what
    happened.
    """
    from apps.bots import supervisor

    reopened = await sync_to_async(_reopen)(bot.id, run.id, live=live)
    if not reopened:
        return False
    fresh = await sync_to_async(_reload)(bot.id)
    if fresh is None:
        return False
    await supervisor.start(fresh)
    return True


def _reopen(bot_id: int, run_id: int, *, live: bool) -> bool:
    run = BotRun.objects.filter(id=run_id).first()
    if run is None:
        return False
    run.stopped_at = None
    run.stop_reason = ""
    run.stop_detail = ""
    # A drill is an unplanned interruption survived, and the gate counts both.
    run.recoveries += 1
    run.unplanned_recoveries += 1
    run.save(
        update_fields=[
            "stopped_at",
            "stop_reason",
            "stop_detail",
            "recoveries",
            "unplanned_recoveries",
        ]
    )
    state = BotState.LIVE if live else BotState.PAPER
    Bot.objects.filter(id=bot_id).update(state=state, dry_run=state != BotState.LIVE)
    return True


def _reload(bot_id: int) -> Bot | None:
    return Bot.objects.filter(id=bot_id).select_related("strategy_version").first()


def _record_halt_drill(bot_id: int, run_id: int) -> tuple[int, tuple[str, ...]]:
    run = BotRun.objects.filter(id=run_id).first()
    drills = 0
    if run is not None:
        run.halt_drills += 1
        run.save(update_fields=["halt_drills"])
        drills = run.halt_drills
    fired = _add_fired(bot_id, HALT_DRILL)
    return drills, fired


def _record_trigger_drill(bot_id: int, trigger: str) -> tuple[int, tuple[str, ...]]:
    run = BotRun.objects.filter(bot_id=bot_id).order_by("-started_at").first()
    return (run.halt_drills if run else 0), _add_fired(bot_id, trigger)


def _add_fired(bot_id: int, name: str) -> tuple[str, ...]:
    bot = Bot.objects.filter(id=bot_id).first()
    if bot is None:
        return ()
    fired = list(bot.drills_fired or [])
    if name not in fired:
        fired.append(name)
        bot.drills_fired = fired
        bot.save(update_fields=["drills_fired", "updated_at"])
    return tuple(fired)


#: Everything the panel offers as a drill button, in the order it shows them.
DRILL_KINDS: tuple[str, ...] = (HALT_DRILL, *(str(trigger) for trigger in DRILL_TRIGGERS))
