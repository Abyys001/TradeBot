"""The Phase 7 promotion gate: `paper → live`, measured rather than asserted.

Every row here is a number the system itself recorded. The panel renders this
and **refuses while any row is unmet** — a gate that knows the numbers, not a
confirmation dialog that asks whether you are sure.

Fourteen days is not round-number thinking: it crosses a weekend, a funding
cycle, an exchange maintenance window, and at least one bad-liquidity hour.

``docs/adapters.md``'s blocker is a row too, and it is the one that cannot be
measured from inside: **no adapter has been run against a live exchange or a
testnet yet.** A bot is a bad first thing to discover that with, so it is
carried here as an explicit human acknowledgement rather than quietly assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "requirement": self.requirement,
            "threshold": self.threshold,
            "measured": self.measured,
            "met": self.met,
        }


def evaluate(bot: Bot) -> dict:
    """Every row, with the number behind it. Never raises; the caller decides."""
    values = settings.BOT
    run = bot.runs.order_by("-started_at").first()
    rows: list[Row] = []

    soak_days = values["SOAK_DAYS"]
    elapsed = _soak_days(run)
    rows.append(
        Row(
            key="soak",
            requirement="continuous paper/shadow runtime",
            threshold=f"{soak_days} days",
            measured=f"{elapsed:.1f} days",
            met=elapsed >= soak_days,
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
        )
    )

    acknowledged = bool((bot.risk_config or {}).get("adapters_tested_on_testnet"))
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
        )
    )

    return {
        "ready": all(row.met for row in rows),
        "rows": [row.as_dict() for row in rows],
    }


def _soak_days(run: BotRun | None) -> float:
    if run is None:
        return 0.0
    end = run.stopped_at or timezone.now()
    return max(0.0, (end - run.started_at) / timedelta(days=1))


def _unexplained_drift(run: BotRun | None) -> int:
    """Actions that were dispatched and never settled. See ``recovery.py``.

    "Unexplained" is precisely this shape: the platform sent something and never
    learned what happened. An action that came back a failure is explained — it
    is a failure.
    """
    if run is None:
        return 0
    return run.actions.filter(dispatched_at__isnull=False, settled_at__isnull=True).count()
