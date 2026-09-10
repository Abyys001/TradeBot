"""Acknowledging the one gate row nothing can measure from inside.

This module used to run **drills** — firing the kill switch and each Q25
auto-stop on purpose to clear two gate rows. Both rows and both drills were
removed at the admin's instruction: they sent real close orders through a live
book to satisfy a checkbox, and an exercise that costs money to pass is not a
safety measure. The auto-stops themselves are untouched — ``riskgate.py`` still
fires all seven for real, and the §7 halt is still one press away in the top
bar of every page.

What is left is the row ``docs/adapters.md`` describes, which is a fact about
the exchanges rather than about this bot: no adapter has been run against a
live exchange or a testnet. No counter can clear that, so a person says so —
and who said it and when are recorded with the answer.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.bots.models import Bot

logger = logging.getLogger(__name__)


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
