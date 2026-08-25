"""`docs/bot-mode.md` §5.1 — the intent → action table, exhaustively.

`plan()` is pure, so every row of that table is a two-line test with no database,
no exchange and no clock. That is the point of keeping it pure.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.bots.models import ActionType
from apps.bots.translate import FLAT, Action, Held, idempotency_key, plan
from apps.pine.intent import Side, StrategyIntent

D = Decimal


def intent(
    side: Side | None,
    *,
    sl: str | None = None,
    tp: str | None = None,
    reason: str = "",
    bar_time: int = 1700000000,
) -> StrategyIntent:
    return StrategyIntent(
        bar_time=bar_time,
        symbol="BTCUSDT",
        desired_side=side,
        sl_pct=D(sl) if sl else None,
        tp_pct=D(tp) if tp else None,
        reason=reason,
        source_span=None,
        plots={},
        alerts=(),
    )


def held(side: Side | None, *, sl: str | None = None, tp: str | None = None, trade_id: int = 7):
    return Held(
        trade_id=trade_id if side else None,
        side=side,
        sl_pct=D(sl) if sl else None,
        tp_pct=D(tp) if tp else None,
    )


def run(i, h, *, sl="1", tp="2") -> list[Action]:
    return plan(intent=i, held=h, default_sl=D(sl), default_tp=D(tp))


# --- the table --------------------------------------------------------------


def test_flat_and_wants_nothing_does_nothing():
    assert run(intent(None), FLAT) == []


def test_flat_and_wants_long_opens_long():
    actions = run(intent(Side.LONG), FLAT)
    assert [a.type for a in actions] == [ActionType.OPEN]
    assert actions[0].side is Side.LONG


def test_flat_and_wants_short_opens_short():
    assert run(intent(Side.SHORT), FLAT)[0].side is Side.SHORT


def test_long_and_wants_long_with_the_same_levels_does_nothing():
    assert run(intent(Side.LONG, sl="1", tp="2"), held(Side.LONG, sl="1", tp="2")) == []


def test_long_and_wants_long_with_new_levels_amends():
    actions = run(intent(Side.LONG, sl="3", tp="6"), held(Side.LONG, sl="1", tp="2"))
    assert [a.type for a in actions] == [ActionType.AMEND]
    assert (actions[0].sl_pct, actions[0].tp_pct) == (D("3"), D("6"))


def test_long_and_wants_flat_closes():
    actions = run(intent(None), held(Side.LONG))
    assert [a.type for a in actions] == [ActionType.CLOSE]
    assert actions[0].trade_id == 7


def test_long_and_wants_short_is_a_close_then_an_open():
    actions = run(intent(Side.SHORT), held(Side.LONG))
    assert [a.type for a in actions] == [ActionType.CLOSE, ActionType.OPEN]


def test_short_and_wants_long_is_also_two_actions():
    actions = run(intent(Side.LONG), held(Side.SHORT))
    assert [a.type for a in actions] == [ActionType.CLOSE, ActionType.OPEN]


def test_the_close_half_of_a_reversal_is_marked_as_one():
    """The dispatcher confirms flat between them; fired together at a netting
    venue the result is a doubled or a cancelled position, and which one it is
    is not something this side gets to decide."""
    close, open_ = run(intent(Side.SHORT), held(Side.LONG))
    assert close.is_reversal_leg is True
    assert open_.is_reversal_leg is False


def test_a_reversal_carries_the_new_sides_levels_on_the_open():
    close, open_ = run(intent(Side.SHORT, sl="4", tp="8"), held(Side.LONG, sl="1", tp="2"))
    assert (open_.sl_pct, open_.tp_pct) == (D("4"), D("8"))


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_the_table_is_total(side):
    """Every (held, desired) pair produces a defined plan, never an exception."""
    for holding in (FLAT, held(Side.LONG), held(Side.SHORT)):
        assert isinstance(run(intent(side), holding), list)


# --- Q21: which percent wins ------------------------------------------------


def test_a_script_percent_beats_the_bots_setting():
    """Q21: a percent `strategy.exit` wins **for that trade**."""
    actions = run(intent(Side.LONG, sl="5", tp="9"), FLAT, sl="1", tp="2")
    assert (actions[0].sl_pct, actions[0].tp_pct) == (D("5"), D("9"))


def test_the_bots_setting_is_the_fallback_not_the_other_way_round():
    actions = run(intent(Side.LONG), FLAT, sl="1", tp="2")
    assert (actions[0].sl_pct, actions[0].tp_pct) == (D("1"), D("2"))


def test_one_side_from_the_script_and_one_from_the_bot():
    actions = plan(
        intent=intent(Side.LONG, sl="5"), held=FLAT, default_sl=D("1"), default_tp=D("2")
    )
    assert (actions[0].sl_pct, actions[0].tp_pct) == (D("5"), D("2"))


def test_a_bot_with_no_levels_configured_and_a_script_with_none_sends_none():
    actions = plan(intent=intent(Side.LONG), held=FLAT, default_sl=None, default_tp=None)
    assert (actions[0].sl_pct, actions[0].tp_pct) == (None, None)


def test_a_level_change_from_the_script_alone_is_enough_to_amend():
    actions = run(intent(Side.LONG, sl="5"), held(Side.LONG, sl="1", tp="2"), sl="1", tp="2")
    assert [a.type for a in actions] == [ActionType.AMEND]


# --- Q20: no quantity anywhere ----------------------------------------------


def test_an_action_carries_no_quantity():
    """Q20: the platform sizes every leg, so there is nowhere for one to hide."""
    action = run(intent(Side.LONG), FLAT)[0]
    assert "qty" not in action.as_dict()
    assert not hasattr(action, "qty")


# --- reasons ----------------------------------------------------------------


def test_the_scripts_reason_rides_along():
    assert run(intent(Side.LONG, reason="golden cross"), FLAT)[0].reason == "golden cross"


def test_an_action_always_has_a_reason_even_with_none_given():
    assert run(intent(Side.LONG), FLAT)[0].reason


def test_a_reversal_says_what_it_is_reversing_to():
    close, _ = run(intent(Side.SHORT), held(Side.LONG))
    assert "short" in close.reason


# --- idempotency ------------------------------------------------------------


def test_the_key_is_the_run_the_bar_and_the_action():
    assert idempotency_key(3, 1700000000, ActionType.OPEN) == "3:1700000000:open"


def test_the_same_bar_evaluated_twice_produces_the_same_key():
    """Which is what makes the UNIQUE constraint refuse the second dispatch."""
    assert idempotency_key(3, 99, ActionType.OPEN) == idempotency_key(3, 99, ActionType.OPEN)


def test_different_runs_of_the_same_bar_are_different_keys():
    assert idempotency_key(3, 99, ActionType.OPEN) != idempotency_key(4, 99, ActionType.OPEN)


def test_the_two_halves_of_a_reversal_do_not_collide():
    """They share the bar, and without the ordinal the open would never place."""
    first = idempotency_key(3, 99, ActionType.CLOSE, 0)
    second = idempotency_key(3, 99, ActionType.OPEN, 1)
    assert first != second
