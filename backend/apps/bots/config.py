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


def platform_properties():
    """The first of ``properties.resolve``'s three layers, from settings.

    **One construction site.** The backtest builds this layer and so does the
    panel's Properties form; when they were two expressions the form showed a
    starting capital of 10,000 beside a report that had used something else,
    and "which of the three won this field" — the whole question that tab
    exists to answer — was being answered against the wrong first layer.
    """
    from apps.pine.properties import StrategyProperties

    return StrategyProperties(
        initial_capital=decimal_setting("BACKTEST_INITIAL_CAPITAL"),
        commission_value=decimal_setting("BACKTEST_FEE_BPS") / Decimal(100),
    )
