"""``settings.BOT`` → typed values, in one place.

The pure package takes its caps as an argument rather than reading settings
(``apps/pine/limits.py`` says why). This is the one module that bridges the two,
so there is exactly one answer to "where did that number come from".
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from apps.pine.limits import Limits


def bot_settings() -> dict:
    return settings.BOT


def limits() -> Limits:
    """The Phase 1/2 caps as the pure package wants them."""
    values = settings.BOT
    return Limits(
        max_script_bytes=values["MAX_SCRIPT_BYTES"],
        max_ast_nodes=values["MAX_AST_NODES"],
        max_ta_call_sites=values["MAX_TA_CALL_SITES"],
        max_loop_iterations=values["MAX_LOOP_ITERATIONS"],
        series_depth=values["SERIES_DEPTH"],
        bar_budget_ms=values["BAR_BUDGET_MS"],
    )


def decimal_setting(key: str) -> Decimal:
    """A ``settings.BOT`` value that is money or a percentage.

    Held as a string in settings and converted here, so no float ever exists
    between the environment and the arithmetic.
    """
    return Decimal(str(settings.BOT[key]))
