"""The bot state machine, as edges rather than as scattered ``if`` statements.

``draft → paper → live``; any state ``→ stopped``; ``stopped → paper`` only.

**``stopped → live`` is deliberately not an edge.** Every one of Q25's triggers
means something was wrong — a run of losses, a drawdown, a feed that gapped, a
script that raised, a state nobody could reconcile. The way back to real money
runs through paper, where the same conditions can be watched without capital
behind them. Making that a rule the database enforces rather than a habit is the
difference between a policy and a hope.
"""

from __future__ import annotations

from apps.bots.models import Bot, BotState

TRANSITIONS: dict[str, frozenset[str]] = {
    BotState.DRAFT: frozenset({BotState.PAPER, BotState.STOPPED}),
    BotState.PAPER: frozenset({BotState.LIVE, BotState.STOPPED}),
    BotState.LIVE: frozenset({BotState.STOPPED}),
    BotState.STOPPED: frozenset({BotState.PAPER}),
}


class IllegalTransition(Exception):
    """Refused. The message names both states so the panel can show it verbatim."""


def check(current: str, target: str) -> None:
    allowed = TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        options = ", ".join(sorted(allowed)) or "nothing"
        extra = ""
        if current == BotState.STOPPED and target == BotState.LIVE:
            extra = (
                " — a bot that stopped goes back to paper first, so whatever stopped it "
                "can be watched without capital behind it"
            )
        raise IllegalTransition(
            f"a bot cannot go from {current} to {target} (only {options}){extra}"
        )


def transition(bot: Bot, target: str) -> Bot:
    """Move ``bot`` to ``target`` or raise. Does not start or stop anything —
    the supervisor watches ``state`` and acts on it, so there is one writer."""
    check(bot.state, target)
    bot.state = target
    # `live` is the only state that routes for real; every other one is a
    # dry run by construction rather than by remembering to set a flag.
    bot.dry_run = target != BotState.LIVE
    bot.save(update_fields=["state", "dry_run", "updated_at"])
    return bot
