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


# --- the refusal has to be actionable, not just correct ---------------------
#
# Reported from live use: a bot whose script manages its own exits was refused
# at the Go-live button, and the panel showed a sentence written before Q37 —
# "Set SL % and TP % on the bot" — which named neither the policy nor the way
# out. The server's own message already said both. These pin the payload the
# panel needs so it can stop inventing one.


def test_the_refusal_names_the_way_out_when_the_script_can_exit():
    """`can_switch` is the difference between a wall and a setting."""
    from apps.bots.supervisor import can_self_exit

    bot = make_bot(source=MANAGED, exit_policy=ExitPolicy.PROTECTED)
    assert protection_gap(bot) != "", "still refused — the levels really are blank"
    assert can_self_exit(bot) is True


def test_a_script_with_no_exit_of_its_own_is_not_offered_the_switch():
    """Offering it here would swap one refusal for a bot that opens a position
    nothing ever closes — which is the failure the strategy-managed gate
    exists to catch."""
    from apps.bots.supervisor import can_self_exit

    bot = make_bot(source=NO_EXIT, exit_policy=ExitPolicy.PROTECTED)
    assert can_self_exit(bot) is False


def test_a_webhook_bot_can_always_exit():
    """Its exits arrive from outside; there is no script to find them in."""
    from apps.bots.supervisor import can_self_exit

    bot = make_bot(
        name="external",
        signal_source=SignalSourceKind.WEBHOOK,
        exit_policy=ExitPolicy.STRATEGY_MANAGED,
    )
    assert can_self_exit(bot) is True


def test_the_protected_refusal_tells_the_operator_both_answers():
    """The message must name the second option, because the panel renders it
    verbatim — a canned string in the panel is exactly what went wrong."""
    bot = make_bot(source=MANAGED, exit_policy=ExitPolicy.PROTECTED)
    gap = protection_gap(bot)
    assert "strategy decides" in gap
    assert "set them on the bot" in gap


# --- over HTTP, which is the surface the panel actually calls ---------------


def _staff_client():
    from django.contrib.auth.models import User
    from django.test import Client

    # get_or_create: one test signs in twice, either side of the field it is
    # about to change, and creating the user again collides on the username.
    User.objects.get_or_create(username="boss", defaults={"is_staff": True})
    user = User.objects.get(username="boss")
    user.set_password("pw")
    user.is_staff = True
    user.save()
    client = Client()
    client.login(username="boss", password="pw")
    return client


def _go_live(bot):
    """Start into live with the promotion gate off, so the refusal under test
    is the protection one rather than the gate's."""
    bot.gate_enforced = False
    bot.save(update_fields=["gate_enforced"])
    return _staff_client().post(
        f"/api/bots/bots/{bot.id}/start/",
        {"state": "live"},
        content_type="application/json",
    )


def test_the_live_refusal_carries_the_reason_and_the_way_out():
    bot = make_bot(source=MANAGED, state="paper", exit_policy=ExitPolicy.PROTECTED)
    response = _go_live(bot)

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "unprotected"
    assert body["can_switch"] is True
    assert body["exit_policy"] == ExitPolicy.PROTECTED
    # The panel renders this verbatim, so it has to say both answers itself.
    assert "strategy decides" in body["detail"]


def test_the_same_bot_goes_live_once_its_exits_are_its_own():
    """The whole point of `can_switch`: one field, and the refusal is gone."""
    bot = make_bot(source=MANAGED, state="paper", exit_policy=ExitPolicy.PROTECTED)
    assert _go_live(bot).status_code == 409

    bot.exit_policy = ExitPolicy.STRATEGY_MANAGED
    bot.save(update_fields=["exit_policy"])

    response = _go_live(bot)
    assert response.status_code == 200, response.json()
    bot.refresh_from_db()
    assert bot.state == "live"


def test_a_script_that_never_exits_is_refused_and_offered_nothing():
    bot = make_bot(source=NO_EXIT, state="paper", exit_policy=ExitPolicy.PROTECTED)
    body = _go_live(bot).json()
    assert body["code"] == "unprotected"
    assert body["can_switch"] is False
