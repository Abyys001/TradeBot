"""The bot's own account of itself — every bar, every decision, in order.

The action log answers "what did it do". This answers the question an operator
actually asks at 03:00, which is **"what was it thinking?"** — and the two are
different, because most bars a bot does nothing, and "nothing" has reasons: the
condition was not met, the position was already right, the gate was closed, the
feed had just been repaired.

Two rules shape the whole module.

  **Nothing here is invented.** Every line is built from a stored ``BotBar``,
  ``BotAction`` or ``BotRun`` field. Where the runtime recorded a reason, that
  reason is quoted; where it recorded plot values, those values are shown. A
  narrator that guessed why a bar was quiet would be the most convincing wrong
  thing on the page.

  **Text is a key, not a sentence.** Each event carries a ``code`` and
  ``params``; the panel renders them through i18n. The alternative — English
  sentences from the server — is untranslatable by construction, and this
  platform ships in six languages. It is also why the variants are numbered:
  the "still watching" line reads differently every few bars so a long quiet
  stretch is scannable, and each variant is a key a translator can see.

Read-only and derived. Nothing is stored: the journal is a projection of rows
that already exist, so it can never disagree with them and retention needs no
second policy (Q26).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.bots.models import ActionType, BotAction, BotBar, BotRun, StopReason

#: Levels the panel colours by. Not severities — a long entry is not "worse"
#: than a quiet bar, it is more interesting, and that is what this ranks.
INFO = "info"
SIGNAL = "signal"
OK = "ok"
WARN = "warn"
DANGER = "danger"

#: How many phrasings each quiet-bar line has. Picked from the bar time, so the
#: same bar always reads the same way — a journal that reshuffled itself on
#: refresh would be unciteable.
WATCHING_VARIANTS = 6
HOLDING_VARIANTS = 4


@dataclass(frozen=True, slots=True)
class Event:
    """One line of the journal."""

    at: int
    kind: str
    code: str
    level: str
    params: dict
    bar_time: int | None = None

    def as_dict(self) -> dict:
        return {
            "at": self.at,
            "kind": self.kind,
            "code": self.code,
            "level": self.level,
            "params": self.params,
            "bar_time": self.bar_time,
        }


def journal(run: BotRun, *, limit: int = 300) -> list[dict]:
    """Every event of this run, newest first, capped at ``limit``.

    The cap is on the *result*, after merging, so a burst of actions cannot
    push every bar off the page or the other way round.
    """
    events: list[Event] = []
    events.extend(_run_events(run))

    bars = list(run.bars.order_by("-bar_time")[:limit])
    # Narration is a diff against the bar before, so walk oldest first and
    # reverse at the end.
    previous: BotBar | None = None
    for bar in reversed(bars):
        events.append(_bar_event(run, bar, previous))
        previous = bar

    for action in run.actions.all()[:limit]:
        events.extend(_action_events(action))

    events.sort(key=lambda event: (event.at, event.kind != "run"), reverse=True)
    return [event.as_dict() for event in events[:limit]]


# --- the run's own milestones -----------------------------------------------


def _run_events(run: BotRun) -> list[Event]:
    started = int(run.started_at.timestamp())
    events = [
        Event(
            at=started,
            kind="run",
            code="started",
            level=OK,
            params={
                "bars": run.warmup_bars,
                "transport": run.feed_source or "",
                "symbol": run.bot.symbol,
                "interval": run.bot.interval,
            },
        )
    ]
    if run.warmup_bars:
        events.append(
            Event(
                at=started,
                kind="run",
                code="warmup",
                level=INFO,
                params={"bars": run.warmup_bars},
            )
        )
    if run.recoveries:
        events.append(
            Event(
                at=started,
                kind="run",
                code="recovered",
                level=WARN,
                params={"n": run.recoveries, "unplanned": run.unplanned_recoveries},
            )
        )
    if run.feed_gaps:
        events.append(
            Event(
                at=started,
                kind="run",
                code="feedGaps",
                level=WARN if run.feed_gaps > run.feed_gaps_repaired else INFO,
                params={"gaps": run.feed_gaps, "repaired": run.feed_gaps_repaired},
            )
        )
    if run.stopped_at is not None:
        events.append(
            Event(
                at=int(run.stopped_at.timestamp()),
                kind="run",
                code="stopped",
                level=DANGER if run.stop_reason != StopReason.MANUAL else WARN,
                params={"reason": run.stop_reason, "detail": run.stop_detail},
            )
        )
    return events


# --- one bar ----------------------------------------------------------------


def _bar_event(run: BotRun, bar: BotBar, previous: BotBar | None) -> Event:
    """What this bar changed, or the fact that it changed nothing.

    The order of the checks *is* the ranking: a reversal outranks an entry,
    an entry outranks a scale-out, and "nothing happened" is what is left.
    """
    intent = bar.intent or {}
    before = (previous.intent or {}) if previous is not None else {}
    side = intent.get("side")
    was = before.get("side")
    params = {
        "close": str(bar.close),
        "plots": _plots(bar),
        "reason": intent.get("reason") or "",
        "side": side,
        "was": was,
        "symbol": run.bot.symbol,
        "interval": run.bot.interval,
        "ms": bar.evaluation_ms,
    }

    if side != was:
        if side and was:
            return _event(bar, "reversal", DANGER, params)
        if side:
            return _event(bar, "signalLong" if side == "long" else "signalShort", SIGNAL, params)
        return _event(bar, "exitSignal", SIGNAL, params)

    fraction = _decimal(intent.get("position_fraction"))
    was_fraction = _decimal(before.get("position_fraction"))
    if side and fraction is not None and was_fraction is not None and fraction < was_fraction:
        params["remaining"] = str((fraction * 100).quantize(Decimal("0.01")))
        return _event(bar, "scaleOut", SIGNAL, params)

    if side and (
        intent.get("sl_pct") != before.get("sl_pct") or intent.get("tp_pct") != before.get("tp_pct")
    ):
        params["sl"] = intent.get("sl_pct")
        params["tp"] = intent.get("tp_pct")
        return _event(bar, "protectionChanged", INFO, params)

    if intent.get("entry_signal") and side:
        # The script asked again on a position it already has. §5 puts 99% into
        # the first entry, so nothing is routed — and saying so is the point:
        # "the script asked and nothing happened" is not the same as silence.
        return _event(bar, "entryRepeated", INFO, params)

    if side:
        variant = bar.bar_time % HOLDING_VARIANTS
        code = f"holding{'Long' if side == 'long' else 'Short'}_{variant}"
        return _event(bar, code, INFO, params)

    variant = bar.bar_time % WATCHING_VARIANTS
    return _event(bar, f"watching_{variant}", INFO, params)


def _event(bar: BotBar, code: str, level: str, params: dict) -> Event:
    return Event(
        at=bar.bar_time, kind="bar", code=code, level=level, params=params, bar_time=bar.bar_time
    )


def _plots(bar: BotBar) -> list[dict]:
    """The script's own plotted values at this bar, in the order it emitted them."""
    return [{"name": name, "value": _short(value)} for name, value in (bar.plots or {}).items()]


def _short(value: object) -> str:
    """A plot value at reading precision. Four places is what an indicator needs."""
    number = _decimal(value)
    if number is None:
        return "" if value is None else str(value)
    quantized = number.quantize(Decimal("0.0001")).normalize()
    return f"{quantized:f}"


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# --- one action -------------------------------------------------------------

#: Action type → the journal code and how loud it is.
_ACTION_CODES = {
    ActionType.OPEN: ("actionOpen", SIGNAL),
    ActionType.CLOSE: ("actionClose", SIGNAL),
    ActionType.AMEND: ("actionAmend", INFO),
    ActionType.REDUCE: ("actionReduce", SIGNAL),
    ActionType.SHADOW: ("actionShadow", INFO),
}


def _action_events(action: BotAction) -> list[Event]:
    code, level = _ACTION_CODES.get(action.action_type, ("actionOther", INFO))
    legs = (action.result or {}).get("legs", [])
    ok_legs = [leg for leg in legs if leg.get("ok")]
    failed = [leg for leg in legs if not leg.get("ok")]
    at = int(action.created_at.timestamp())

    intent = action.intent or {}
    events = [
        Event(
            at=at,
            kind="action",
            code=code if action.ok or action.action_type == ActionType.SHADOW else f"{code}Failed",
            level=level if action.ok or action.action_type == ActionType.SHADOW else DANGER,
            params={
                "side": intent.get("side"),
                "reason": action.reason or intent.get("reason") or "",
                "accounts": len(ok_legs),
                "total": len(legs),
                "error": action.error,
                "fraction": intent.get("fraction"),
                "sl": intent.get("sl_pct"),
                "tp": intent.get("tp_pct"),
                "shadow": action.action_type == ActionType.SHADOW,
            },
            bar_time=action.bar_time,
        )
    ]
    if failed:
        events.append(
            Event(
                at=at,
                kind="action",
                code="legsFailed",
                level=WARN,
                params={
                    "n": len(failed),
                    "accounts": [
                        {
                            "label": leg.get("account_label") or f"#{leg.get('account_id')}",
                            "code": leg.get("code") or "",
                        }
                        for leg in failed
                    ],
                },
                bar_time=action.bar_time,
            )
        )
    if action.unsettled:
        events.append(
            Event(
                at=at,
                kind="action",
                code="unsettled",
                level=DANGER,
                params={},
                bar_time=action.bar_time,
            )
        )
    return events
