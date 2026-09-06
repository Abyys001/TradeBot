"""The Phase 7 promotion gate: `paper → live`, measured rather than asserted.

Every row here is a number the system itself recorded. The panel renders this
and **refuses while any row is unmet** — a gate that knows the numbers, not a
confirmation dialog that asks whether you are sure.

Fourteen days is not round-number thinking: it crosses a weekend, a funding
cycle, an exchange maintenance window, and at least one bad-liquidity hour.

``docs/adapters.md``'s blocker is a row too, and it is the one that cannot be
measured from inside: **no adapter has been run against a live exchange or a
testnet yet.** A bot is a bad first thing to discover that with, so it is
carried here as an explicit human acknowledgement rather than quietly assumed —
tickable from the panel (``drills.acknowledge_adapters``), which records who
ticked it and when. A gate that can only be cleared from a shell is a gate
people route around.

Every row carries ``params`` beside its English sentence. The panel renders
``bots.gate.<key>`` with those params, so the gate reads in all six languages
without the server growing an opinion about which one the reader wants. The
English text stays because it is what the API has always said and what a log
line quotes.

The soak row also carries **seconds**, not days. "14 days required, 0.5 days
measured" tells an operator nothing about when to come back; the panel counts
down in days, hours and minutes off ``seconds``/``required_seconds`` and ticks
it live, so the wait is a number that visibly moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.bots.models import Bot, BotRun, StopReason

#: Q25's seven, all of which must have been fired deliberately in a drill.
DRILL_TRIGGERS = (
    StopReason.CONSECUTIVE_LOSSES,
    StopReason.DRAWDOWN,
    StopReason.FEED_GAP,
    StopReason.SCRIPT_ERROR,
    StopReason.STATE_DISAGREEMENT,
    StopReason.TRADE_RATE,
    StopReason.NO_BARS,
)


@dataclass(frozen=True, slots=True)
class Row:
    key: str
    requirement: str
    threshold: str
    measured: str
    met: bool
    #: What the panel interpolates into ``bots.gate.<key>``. Numbers, never
    #: prose — a translated sentence must be able to put them anywhere.
    params: dict = field(default_factory=dict)
    #: True when a person can clear this row from the panel (the adapters
    #: acknowledgement) or fire what clears it (a drill). The rows that are
    #: pure measurement carry False and the panel offers no control.
    actionable: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "requirement": self.requirement,
            "threshold": self.threshold,
            "measured": self.measured,
            "met": self.met,
            "params": self.params,
            "actionable": self.actionable,
        }


def evaluate(bot: Bot) -> dict:
    """Every row, with the number behind it. Never raises; the caller decides."""
    values = settings.BOT
    run = bot.runs.order_by("-started_at").first()
    rows: list[Row] = []

    soak_days = values["SOAK_DAYS"]
    elapsed_seconds = _soak_seconds(run)
    required_seconds = int(soak_days * 86400)
    rows.append(
        Row(
            key="soak",
            requirement="continuous paper/shadow runtime",
            threshold=f"{soak_days} days",
            measured=_duration(elapsed_seconds),
            met=elapsed_seconds >= required_seconds,
            params={
                "days": soak_days,
                "seconds": elapsed_seconds,
                "required_seconds": required_seconds,
                # The instant the clock started, so the panel can tick without
                # asking the server again. A countdown that only moves on
                # refresh is a number, not a countdown.
                "since": run.started_at.isoformat() if run is not None else None,
                "running": bool(run is not None and run.stopped_at is None),
                "remaining_seconds": max(0, required_seconds - elapsed_seconds),
            },
        )
    )

    divergences = run.divergences if run else 0
    rows.append(
        Row(
            key="divergence",
            requirement="unexplained backtest/live divergences",
            threshold="0",
            measured=str(divergences),
            met=divergences == 0,
            params={"n": divergences},
        )
    )

    recoveries = run.recoveries if run else 0
    unplanned = run.unplanned_recoveries if run else 0
    rows.append(
        Row(
            key="restarts",
            requirement="process restarts survived cleanly",
            threshold=f"≥ {values['SOAK_MIN_RESTARTS']}, at least one unplanned",
            measured=f"{recoveries} ({unplanned} unplanned)",
            met=recoveries >= values["SOAK_MIN_RESTARTS"] and unplanned >= 1,
            params={
                "n": recoveries,
                "unplanned": unplanned,
                "required": values["SOAK_MIN_RESTARTS"],
            },
        )
    )

    gaps = run.feed_gaps if run else 0
    repaired = run.feed_gaps_repaired if run else 0
    rows.append(
        Row(
            key="feed_gaps",
            requirement="feed gaps repaired or cleanly stopped",
            threshold="100%",
            measured=f"{repaired}/{gaps}" if gaps else "no gaps seen",
            met=gaps == 0 or repaired >= gaps,
            params={"gaps": gaps, "repaired": repaired},
        )
    )

    drift = _unexplained_drift(run)
    rows.append(
        Row(
            key="drift",
            requirement="reconciliation drift events",
            threshold="0 unexplained",
            measured=str(drift),
            met=drift == 0,
            params={"n": drift},
        )
    )

    drills = run.halt_drills if run else 0
    rows.append(
        Row(
            key="halt_drills",
            requirement="kill-switch drills passed",
            threshold=f"≥ {values['SOAK_MIN_HALT_DRILLS']}",
            measured=str(drills),
            met=drills >= values["SOAK_MIN_HALT_DRILLS"],
            params={"n": drills, "required": values["SOAK_MIN_HALT_DRILLS"]},
            # Firing this one is a button on the bot's page: it engages the
            # halt, force-closes every open trade without asking the strategy,
            # and resumes the bot into the same run. See ``drills.py``.
            actionable="halt_drill",
        )
    )

    fired = set(bot.drills_fired or [])
    missing = [t for t in DRILL_TRIGGERS if t not in fired]
    rows.append(
        Row(
            key="q25_drills",
            requirement="every Q25 auto-stop fired deliberately in a drill",
            threshold=f"all {len(DRILL_TRIGGERS)}",
            measured=f"{len(fired & set(DRILL_TRIGGERS))}/{len(DRILL_TRIGGERS)}"
            + (f" (missing: {', '.join(missing)})" if missing else ""),
            met=not missing,
            params={
                "done": len(fired & set(DRILL_TRIGGERS)),
                "total": len(DRILL_TRIGGERS),
                "missing": [str(trigger) for trigger in missing],
            },
            actionable="trigger_drill",
        )
    )

    configured = bool(bot.risk_config)
    rows.append(
        Row(
            key="risk_config",
            requirement="Q25 limits set deliberately for this strategy",
            threshold="not left at defaults",
            measured="set" if configured else "still the settings.BOT defaults",
            met=configured,
            params={"set": configured},
        )
    )

    config = bot.risk_config or {}
    acknowledged = bool(config.get("adapters_tested_on_testnet"))
    rows.append(
        Row(
            key="adapters",
            requirement=(
                "docs/adapters.md blocker cleared — the exchanges involved have been run "
                "against a live exchange or testnet"
            ),
            threshold="acknowledged by a person",
            measured="acknowledged" if acknowledged else "not acknowledged",
            met=acknowledged,
            params={
                "acknowledged": acknowledged,
                "by": config.get("adapters_acknowledged_by") or "",
                "at": config.get("adapters_acknowledged_at") or "",
            },
            actionable="acknowledge_adapters",
        )
    )

    return {
        "ready": all(row.met for row in rows),
        "rows": [row.as_dict() for row in rows],
    }


def _soak_seconds(run: BotRun | None) -> int:
    """How long this run has been going, in seconds.

    Seconds and not days because the panel counts down in days, hours and
    minutes: "0.5 days" is a number an operator cannot plan around, and the
    rounding is what made the row look frozen for hours at a time.
    """
    if run is None:
        return 0
    end = run.stopped_at or timezone.now()
    return max(0, int((end - run.started_at) / timedelta(seconds=1)))


def _duration(seconds: int) -> str:
    """``3d 04h 17m`` — the same breakdown the panel shows, for the API and logs."""
    days, rest = divmod(max(0, seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _unexplained_drift(run: BotRun | None) -> int:
    """Actions that were dispatched and never settled. See ``recovery.py``.

    "Unexplained" is precisely this shape: the platform sent something and never
    learned what happened. An action that came back a failure is explained — it
    is a failure.
    """
    if run is None:
        return 0
    return run.actions.filter(dispatched_at__isnull=False, settled_at__isnull=True).count()
