"""The exit the platform takes on its own, when the venue's did not.

A stop that was sent to an exchange and is no longer there looks exactly like
one that is quietly waiting — there is no callback saying "your stop is gone" —
so the platform watches the level itself and closes the position from this side
when a bar reaches it. ``apps/bots/exitguard.py`` has the argument.

Two properties are the whole of it, and they pull in opposite directions:

  * it must fire on the bar that reaches the level, for either side, under
    either Q5a basis, and whether the level is a stop, a target or the Q37
    safety net;
  * it must never invent one. Every number comes off the ``Trade`` row the
    platform wrote, and a trade with nothing recorded gets nothing enforced.

It is deliberately the **backtest's** rule and not a second one: `_check_exits`
closes a simulated position on the bar whose range reaches its level, stop
first when one bar touches both, and this makes the same comparison — so
switching it on moves live towards the report rather than away from it.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest
from django.conf import settings
from django.test import override_settings

from apps.bots import exitguard
from apps.pine.bar import Bar

ENTRY = D("100")


def bar(high: str, low: str, *, time: int = 1_000) -> Bar:
    return Bar(
        time=time,
        open=ENTRY,
        high=D(high),
        low=D(low),
        close=D(high),
        volume=D("1"),
    )


def check(**kwargs):
    defaults = dict(
        side="long",
        entry=ENTRY,
        sl_pct=D("2"),
        tp_pct=D("4"),
        safety_net_pct=None,
        leverage=1,
        basis="price",
    )
    return exitguard.check(**{**defaults, **kwargs})


# --- it fires on the bar that reaches the level -----------------------------


def test_a_long_whose_bar_reached_the_stop_is_an_exit_signal():
    breach = check(bar=bar("101", "97"))
    assert breach is not None
    assert breach.kind == exitguard.STOP
    assert breach.level == D("98")
    assert breach.reached == D("97")
    assert breach.reason == "exit signal: stop"


def test_a_long_whose_bar_reached_the_target_is_an_exit_signal():
    breach = check(bar=bar("105", "99.5"))
    assert breach is not None and breach.kind == exitguard.TARGET
    assert breach.level == D("104")


def test_a_short_reads_the_bar_the_other_way_round():
    """The stop is above and the target below, so high and low swap roles."""
    assert check(side="short", bar=bar("103", "99")).kind == exitguard.STOP
    assert check(side="short", bar=bar("100.5", "95")).kind == exitguard.TARGET


def test_a_bar_that_touched_neither_is_not_an_exit():
    assert check(bar=bar("101", "99")) is None


def test_exactly_at_the_level_counts_as_reached():
    """A stop is a price, not a strict inequality — the venue would have filled."""
    assert check(bar=bar("101", "98")).kind == exitguard.STOP
    assert check(bar=bar("104", "99")).kind == exitguard.TARGET


def test_one_bar_that_touched_both_is_read_as_the_stop():
    """The pessimistic reading, and the one the backtest's own header states.

    Without tick data there is no honest answer, so both sides of the platform
    have to give the *same* wrong-in-the-same-direction one, or a report and
    the live loop it predicts disagree on exactly the bars that matter most.
    """
    breach = check(bar=bar("105", "97"))
    assert breach.kind == exitguard.STOP


def test_the_margin_basis_puts_the_level_where_the_platform_would_have(settings):
    """Q5a: at 10x a 2% *margin* stop is a 0.2% price move, not a 2% one."""
    settings.TRADING = {**settings.TRADING, "SLTP_BASIS": "margin"}
    breach = check(bar=bar("101", "99.8"), leverage=10, basis="margin")
    assert breach is not None and breach.level == D("99.80")
    # The same bar is nowhere near a price-basis stop.
    assert check(bar=bar("101", "99.8"), leverage=10, basis="price") is None


# --- the safety net ---------------------------------------------------------


def test_the_safety_net_is_enforced_when_there_is_no_stop():
    """Q37: what rests at the venue for a strategy-managed trade is enforced here too."""
    breach = check(sl_pct=None, tp_pct=None, safety_net_pct=D("10"), bar=bar("101", "89"))
    assert breach is not None and breach.kind == exitguard.SAFETY_NET
    assert breach.level == D("90")


def test_a_real_stop_wins_over_the_net_so_only_one_level_is_ever_watched():
    """Q5d: two stops on one position is the state that rule exists to prevent."""
    breach = check(sl_pct=D("2"), safety_net_pct=D("10"), bar=bar("101", "89"))
    assert breach.kind == exitguard.STOP
    assert breach.level == D("98")


# --- it never invents one ---------------------------------------------------


def test_a_trade_with_no_levels_recorded_has_nothing_to_enforce():
    """The common strategy-managed case. Reported as unprotected, not guessed at."""
    assert check(sl_pct=None, tp_pct=None, safety_net_pct=None, bar=bar("200", "1")) is None


def test_a_trade_with_no_entry_price_is_not_guessed_from_the_bar():
    """An unconfirmed entry has no admin price yet, and a level off a bar close
    would be a stop nobody put there."""
    assert check(entry=None, bar=bar("200", "1")) is None
    assert check(entry=D("0"), bar=bar("200", "1")) is None


def test_the_switch_turns_it_off_without_turning_anything_else_off():
    with override_settings(BOT={**settings.BOT, "EXIT_GUARD": False}):
        assert exitguard.enabled() is False


def test_the_switch_is_on_by_default():
    assert exitguard.enabled() is True


# --- against a stored trade row ---------------------------------------------


@pytest.mark.django_db
def test_for_trade_reads_the_row_rather_than_todays_settings():
    """``Trade.sltp_basis`` is recorded per trade for exactly this reason: a
    percentage written under one reading and enforced under another is a stop
    somewhere nobody put it."""
    from apps.trading.models import Trade

    trade = Trade.objects.create(
        symbol="BTCUSDT",
        side="long",
        leverage=10,
        sl_pct=D("2"),
        tp_pct=None,
        sltp_basis="margin",
        admin_entry_price=ENTRY,
    )
    with override_settings(TRADING={**settings.TRADING, "SLTP_BASIS": "price"}):
        breach = exitguard.for_trade(trade, bar("101", "99.8"))
    assert breach is not None and breach.level == D("99.80")


@pytest.mark.django_db
def test_for_trade_on_nothing_held_is_nothing():
    assert exitguard.for_trade(None, bar("200", "1")) is None
