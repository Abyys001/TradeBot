"""What a bot does before it is allowed to do anything else, after a restart.

The hard part of Phase 6, and the order is the substance:

  **Re-warm from bars, never from a serialised snapshot.** The runtime *has*
  ``snapshot()``/``restore()`` and this deliberately does not use them across a
  restart: a code change silently invalidates a snapshot, and "silently" is the
  operative word — the bot would start with converged-looking state that belongs
  to a different implementation of the same indicator. Re-warming is slower and
  always correct.

  **Read the position from the exchange, per account.** Not from this database.

  **Reconcile any action recorded as dispatched whose result is unknown.**
  That is exactly the shape a restart mid-fan-out leaves behind, and it goes
  through the *existing* ``confirm_open`` path — a leg that failed after its
  order went out may be holding a position, and the bot must respect the same
  ``NEVER_SENT_CODES`` asymmetry the manual path does or it will re-enter into
  an account that is already in.

  **A disagreement is retried once and then stops the bot.** Auto-correcting a
  disagreement nobody understands is how a recovery becomes a liquidation
  (Q25). The retry exists because one pass can catch an exchange mid-settlement;
  the second is where "I do not know what is true" becomes an answer.
"""

from __future__ import annotations

import logging

from asgiref.sync import sync_to_async

from apps.bots.models import Bot, BotAction, BotRun, StopReason
from apps.bots.riskgate import limit_for
from apps.logging.utils import system_log

logger = logging.getLogger(__name__)


class StateDisagreement(Exception):
    """The exchange and the bot's record still disagree. Q25 stops the bot."""


async def reconcile_run(bot: Bot, run: BotRun) -> dict:
    """Settle everything left in the air, or refuse to continue. Logs one entry."""
    from apps.trading import possync, services

    unsettled = await sync_to_async(_unsettled_actions)(run)
    report = {
        "run_id": run.id,
        "unsettled_actions": len(unsettled),
        "passes": 0,
        "resolved": [],
        "unresolved": [],
    }

    passes = int(limit_for(bot, "RECONCILE_PASSES_BEFORE_STOP"))
    for attempt in range(1, max(1, passes) + 1):
        report["passes"] = attempt
        # The existing paths, not a bot-specific copy of them: `confirm_open`
        # re-reads accounts whose entry outcome is unknown, `sync_positions`
        # writes what the exchange says about every account.
        try:
            await services.reconcile_open_trade()
            await possync.sync_positions(force=True)
        except Exception as exc:  # noqa: BLE001 - an unreachable venue is not a verdict
            logger.warning("bot %s recovery pass %d could not read: %s", bot.id, attempt, exc)

        still_open = await sync_to_async(_unsettled_actions)(run)
        settled = [a.id for a in unsettled if a.id not in {b.id for b in still_open}]
        report["resolved"] = settled
        if not still_open:
            break
        report["unresolved"] = [a.id for a in still_open]

    if report["unresolved"]:
        detail = (
            f"{len(report['unresolved'])} action(s) are still recorded as dispatched with "
            f"no known result after {report['passes']} reconcile pass(es). This bot will "
            f"not trade until a person has looked at them."
        )
        system_log(
            "CRITICAL",
            "BOT",
            detail,
            source="apps.bots.recovery",
            error_code=StopReason.STATE_DISAGREEMENT,
            context=report,
        )
        raise StateDisagreement(detail)

    system_log(
        "INFO",
        "BOT",
        (
            f"bot {bot.name} recovered: {report['unsettled_actions']} unsettled action(s), "
            f"{len(report['resolved'])} reconciled in {report['passes']} pass(es)"
        ),
        source="apps.bots.recovery",
        context=report,
    )
    return report


def _unsettled_actions(run: BotRun) -> list[BotAction]:
    """Dispatched, never settled. The shape a restart mid-fan-out leaves."""
    return list(
        BotAction.objects.filter(
            run=run, dispatched_at__isnull=False, settled_at__isnull=True
        ).order_by("id")
    )


@sync_to_async
def note_unplanned_restart(run: BotRun) -> None:
    """Count a restart nobody asked for. The Phase 7 gate needs at least one.

    "Unplanned" is inferred rather than declared: a run that still had an
    unsettled action when the process came back was not shut down cleanly, and
    ``shutdown()`` never leaves one.
    """
    if _unsettled_actions(run):
        run.unplanned_recoveries += 1
        run.save(update_fields=["unplanned_recoveries"])
