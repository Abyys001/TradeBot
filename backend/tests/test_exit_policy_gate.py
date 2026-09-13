"""Q37's start-up check: the question changes with the policy.

`supervisor.protection_gap` used to ask one thing — "can this bot supply a stop
and a target?" — because every order needed both. Under `strategy_managed` that
question is answered by the policy, and a sharper one takes its place: **can
this script ever close a position?**

A protected bot with no exit logic is merely inefficient; its stop or its target
ends the trade eventually. A strategy-managed one with no exit logic opens a
position that nothing will ever close, which is the single new failure this
policy makes possible. Both are refused at the button, to somebody who can fix
them, rather than at three in the morning to nobody.
"""

from __future__ import annotations

import pytest

from apps.bots.models import ExitPolicy, SignalSourceKind
from apps.bots.supervisor import protection_gap
from tests.bot_factory import make_bot

pytestmark = pytest.mark.django_db

# Enters on a cross and exits with strategy.close — the shape Q37 is about.
MANAGED = """
//@version=5
strategy("managed exits", overlay = true)
fast = ta.sma(close, 9)
slow = ta.sma(close, 21)
if ta.crossover(fast, slow)
    strategy.entry("L", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("L")
"""

# Enters and never exits. Harmless under a stop and a target; a trap without.
NO_EXIT = """
//@version=5
strategy("no exits", overlay = true)
if ta.crossover(ta.sma(close, 9), ta.sma(close, 21))
    strategy.entry("L", strategy.long)
"""


def test_a_protected_bot_with_no_levels_is_still_refused():
    """The rule as it was: blank percentages and no percent strategy.exit."""
    bot = make_bot(source=MANAGED, exit_policy=ExitPolicy.PROTECTED)
    gap = protection_gap(bot)
    assert "no stop loss" in gap
    # And it now points at the way out, which is the whole of what Q37 added.
    assert "strategy decides" in gap


def test_a_protected_bot_with_levels_passes_exactly_as_before():
    bot = make_bot(
        source=MANAGED, exit_policy=ExitPolicy.PROTECTED, sl_pct="2", tp_pct="4"
    )
    assert protection_gap(bot) == ""


def test_a_strategy_managed_bot_needs_no_levels():
    bot = make_bot(source=MANAGED, exit_policy=ExitPolicy.STRATEGY_MANAGED)
    assert protection_gap(bot) == ""


def test_a_strategy_managed_bot_that_can_never_close_is_refused():
    """The one failure this policy introduces, caught where it can be fixed."""
    bot = make_bot(source=NO_EXIT, exit_policy=ExitPolicy.STRATEGY_MANAGED)
    gap = protection_gap(bot)
    assert "never calls strategy.close" in gap


def test_that_same_script_is_fine_under_a_stop_and_a_target():
    """Because there, something else ends the trade."""
    bot = make_bot(
        source=NO_EXIT, exit_policy=ExitPolicy.PROTECTED, sl_pct="2", tp_pct="4"
    )
    assert protection_gap(bot) == ""


def test_a_webhook_bot_is_exempt_from_both_questions():
    """Its exits arrive from outside; there is no script to read them off."""
    bot = make_bot(
        name="external",
        signal_source=SignalSourceKind.WEBHOOK,
        exit_policy=ExitPolicy.STRATEGY_MANAGED,
    )
    assert bot.strategy_version is None
    assert protection_gap(bot) == ""
