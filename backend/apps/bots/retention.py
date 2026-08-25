"""Q26: what is kept, and for how long.

The split is not about disk. ``BotAction`` and the intent that produced it are
the **audit trail** — what the bot decided, when, why, and which legs came back —
and they are kept forever because that is what accountability for other people's
capital means. Bars are the *volume*: 1,440 rows a day per bot at 1m, none of
which the audit trail depends on.

So: at 15m and above every evaluated bar is kept for the bot's lifetime. At 1m
and 5m only the bars where a signal or a plot value changed, plus a rolling
seven-day full window for debugging. Trimming loses detail, never accountability.
"""

from __future__ import annotations

import logging
import time

from apps.bots.models import BotBar, BotRun

logger = logging.getLogger(__name__)

#: Intervals dense enough to need trimming at all.
DENSE_INTERVALS = frozenset({"1m", "5m"})

#: How much unconditional history a dense interval keeps, in seconds.
DEBUG_WINDOW_SECONDS = 7 * 24 * 3600


def keeps_every_bar(interval: str) -> bool:
    return interval not in DENSE_INTERVALS


def trim(run: BotRun, *, now: int | None = None) -> int:
    """Delete the bars Q26 does not keep. Returns how many went.

    Idempotent and safe to call on every bar — it deletes by an indexed range,
    so the cost is a bounded query rather than a scan.
    """
    if keeps_every_bar(run.bot.interval):
        return 0
    cutoff = (now or int(time.time())) - DEBUG_WINDOW_SECONDS
    deleted, _ = BotBar.objects.filter(run=run, bar_time__lt=cutoff, changed=False).delete()
    if deleted:
        logger.debug("bot run %s: trimmed %d unchanged bars older than %s", run.id, deleted, cutoff)
    return deleted


def is_change(previous: dict | None, intent: dict, plots: dict) -> bool:
    """Whether this bar differs from the one before it in any way worth keeping.

    A signal change or any plot value moving counts. Everything else on a 1m
    chart is the same bar drawn again.
    """
    if previous is None:
        return True
    if previous.get("intent", {}).get("side") != intent.get("side"):
        return True
    if previous.get("intent", {}).get("sl_pct") != intent.get("sl_pct"):
        return True
    if previous.get("intent", {}).get("tp_pct") != intent.get("tp_pct"):
        return True
    return previous.get("plots") != plots
