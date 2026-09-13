"""Q37 — a strategy exit is a trading instruction, not a threshold.

The spec's §3 rule ("both are required") is now one of two policies rather than
the only one, and these are the tests that say which parts of it survived:

  * a ``protected`` order is refused without both, exactly as before — every
    row that existed before Q37 is one of these, so this is the regression test
    for "nothing changed for anybody who did not ask for it";
  * a ``strategy_managed`` order routes with neither;
  * an exit closes a position **at any PnL**, with no percentage configured at
    all, which is the sentence the whole change exists to make true;
  * the safety net rests at the venue only in a real stop's absence.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.bots.models import ActionType
from apps.bots.translate import FLAT, Held, plan
from apps.pine.intent import Side, StrategyIntent
from apps.trading.protection import (
    DEFAULT_POLICY,
    ExitPolicy,
    ProtectionInvalid,
    ProtectionRequired,
    parse_policy,
    resolve,
)

D = Decimal


def intent(side: Side | None, **kwargs) -> StrategyIntent:
    return StrategyIntent(bar_time=1, symbol="BTCUSDT", desired_side=side, **kwargs)


# --- the policy itself ------------------------------------------------------


def test_the_default_is_the_rule_as_it_was():
    """Nothing that predates Q37 changes behaviour. The whole premise."""
    assert DEFAULT_POLICY is ExitPolicy.PROTECTED
    with pytest.raises(ProtectionRequired):
        resolve(sl_pct=D("2"))
    with pytest.raises(ProtectionRequired):
        resolve(tp_pct=D("4"))
    assert resolve(sl_pct=D("2"), tp_pct=D("4")).resting_sl == D("2")


def test_a_strategy_managed_order_needs_neither():
    protection = resolve(policy=ExitPolicy.STRATEGY_MANAGED)
    assert protection.resting_sl is None
    assert protection.resting_tp is None
    assert protection.unprotected is True


def test_one_side_alone_is_legal_when_the_strategy_manages_the_other():
    """A take profit plus a strategy-decided stop is a real configuration."""
    protection = resolve(policy=ExitPolicy.STRATEGY_MANAGED, tp_pct=D("5"))
    assert protection.resting_tp == D("5")
    assert protection.resting_sl is None
    assert protection.unprotected is False


def test_the_safety_net_rests_only_where_no_real_stop_does():
    net = resolve(policy=ExitPolicy.STRATEGY_MANAGED, safety_net_pct=D("20"))
    assert net.resting_sl == D("20")
    assert net.net_engaged is True

    both = resolve(policy=ExitPolicy.STRATEGY_MANAGED, sl_pct=D("2"), safety_net_pct=D("20"))
    assert both.resting_sl == D("2"), "the real stop wins; two stops is Q5d's failure"
    assert both.net_engaged is False


def test_a_net_inside_the_stop_is_refused_rather_than_stored_doing_nothing():
    with pytest.raises(ProtectionInvalid):
        resolve(policy=ExitPolicy.STRATEGY_MANAGED, sl_pct=D("20"), safety_net_pct=D("5"))


def test_a_net_is_dropped_under_the_protected_policy():
    """It could never engage there, and a stored number that does nothing reads
    on the panel as protection that exists."""
    assert resolve(sl_pct=D("2"), tp_pct=D("4"), safety_net_pct=D("20")).safety_net_pct is None


def test_the_bounds_are_unchanged_by_the_policy():
    """A blank is an instruction; a typo is still a typo."""
    for policy in ExitPolicy:
        with pytest.raises(ProtectionInvalid):
            resolve(policy=policy, sl_pct=D("-1"), tp_pct=D("4"))
        with pytest.raises(ProtectionInvalid):
            resolve(policy=policy, sl_pct=D("140"), tp_pct=D("4"))
    # A 250% target is a real thing to ask for, under either policy.
    assert resolve(sl_pct=D("2"), tp_pct=D("250")).resting_tp == D("250")


def test_an_unknown_policy_is_refused_never_defaulted():
    """Defaulting it would silently override the exits of a caller who typoed."""
    with pytest.raises(ProtectionInvalid):
        parse_policy("strategy-managed")
    assert parse_policy(None) is ExitPolicy.PROTECTED
    assert parse_policy("") is ExitPolicy.PROTECTED


def test_the_database_spelling_matches_the_module(db):
    """The two enums are declared apart (a migration must not import a module
    that may move). This is what keeps them from drifting."""
    from apps.bots.models import ExitPolicy as DbPolicy

    assert {p.value for p in DbPolicy} == {p.value for p in ExitPolicy}


# --- the exit, which is the point -------------------------------------------


def test_an_exit_closes_with_no_percentages_configured_anywhere():
    """The sentence Q37 exists to make true.

    No stop, no target, nothing on the bot — and the strategy saying "flat"
    still produces a close. Nothing on this path reads PnL.
    """
    held = Held(trade_id=7, side=Side.LONG, sl_pct=None, tp_pct=None)
    actions = plan(
        intent=intent(None, reason="structure broke"),
        held=held,
        default_sl=None,
        default_tp=None,
        policy=ExitPolicy.STRATEGY_MANAGED,
    )
    assert [a.type for a in actions] == [ActionType.CLOSE]
    assert actions[0].trade_id == 7
    assert actions[0].reason == "structure broke"


def test_an_exit_closes_a_losing_position_just_the_same():
    """There is no branch that declines to close because a target was not hit —
    this asserts the absence by routing an exit under every policy."""
    held = Held(trade_id=7, side=Side.SHORT, sl_pct=D("2"), tp_pct=D("4"))
    for policy in ExitPolicy:
        actions = plan(
            intent=intent(None),
            held=held,
            default_sl=D("2"),
            default_tp=D("4"),
            policy=policy,
        )
        assert [a.type for a in actions] == [ActionType.CLOSE]


def test_an_entry_under_the_strategy_policy_carries_blanks_and_the_net():
    actions = plan(
        intent=intent(Side.LONG),
        held=FLAT,
        default_sl=None,
        default_tp=None,
        policy=ExitPolicy.STRATEGY_MANAGED,
        safety_net=D("20"),
    )
    assert [a.type for a in actions] == [ActionType.OPEN]
    assert actions[0].sl_pct is None
    assert actions[0].tp_pct is None
    assert actions[0].safety_net_pct == D("20")
    assert actions[0].exit_policy == ExitPolicy.STRATEGY_MANAGED


def test_the_net_is_not_carried_under_the_protected_policy():
    actions = plan(
        intent=intent(Side.LONG),
        held=FLAT,
        default_sl=D("2"),
        default_tp=D("4"),
        policy=ExitPolicy.PROTECTED,
        safety_net=D("20"),
    )
    assert actions[0].safety_net_pct is None


def test_a_strategy_managed_bot_does_not_amend_itself_every_bar():
    """Both sides blank on the bot and blank in the intent: nothing changed, so
    nothing is sent. Without this a bot with no levels would fan out an amend on
    every single bar it evaluated."""
    held = Held(trade_id=7, side=Side.LONG, sl_pct=None, tp_pct=None)
    actions = plan(
        intent=intent(Side.LONG),
        held=held,
        default_sl=None,
        default_tp=None,
        policy=ExitPolicy.STRATEGY_MANAGED,
        safety_net=D("20"),
    )
    assert actions == []


def test_a_reversal_is_still_two_sequenced_actions_under_either_policy():
    held = Held(trade_id=7, side=Side.SHORT, sl_pct=None, tp_pct=None)
    actions = plan(
        intent=intent(Side.LONG),
        held=held,
        default_sl=None,
        default_tp=None,
        policy=ExitPolicy.STRATEGY_MANAGED,
    )
    assert [a.type for a in actions] == [ActionType.CLOSE, ActionType.OPEN]
    assert actions[0].is_reversal_leg is True


# --- the idempotency key the webhook shares ---------------------------------


def test_the_bar_key_is_byte_for_byte_what_it_always_was():
    """Existing BotAction rows have to keep matching, or a restart mid-fan-out
    stops being caught for every bot that predates Q37."""
    from apps.bots.translate import idempotency_key

    assert idempotency_key(3, 1700000000, "open") == "3:1700000000:open"
    assert idempotency_key(3, 1700000000, "open", 1) == "3:1700000000:open:1"


def test_a_signal_key_cannot_collide_with_a_bar_key():
    from apps.bots.translate import idempotency_key

    bar = idempotency_key(3, 42, "open")
    signal = idempotency_key(3, 42, "open", 0, "sig")
    assert bar != signal
