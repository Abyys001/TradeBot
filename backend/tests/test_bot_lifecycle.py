"""The state machine, and Q26's retention split."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from apps.bots import lifecycle, retention
from apps.bots.lifecycle import IllegalTransition
from apps.bots.models import BotBar, BotState
from tests.bot_factory import make_bot, make_run

D = Decimal

pytestmark = pytest.mark.django_db


# --- transitions ------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BotState.DRAFT, BotState.PAPER),
        (BotState.DRAFT, BotState.STOPPED),
        (BotState.PAPER, BotState.LIVE),
        (BotState.PAPER, BotState.STOPPED),
        (BotState.LIVE, BotState.STOPPED),
        (BotState.STOPPED, BotState.PAPER),
    ],
)
def test_the_allowed_edges(current, target):
    lifecycle.check(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BotState.DRAFT, BotState.LIVE),
        (BotState.STOPPED, BotState.LIVE),
        (BotState.LIVE, BotState.PAPER),
        (BotState.PAPER, BotState.DRAFT),
        (BotState.STOPPED, BotState.DRAFT),
    ],
)
def test_the_refused_edges(current, target):
    with pytest.raises(IllegalTransition):
        lifecycle.check(current, target)


def test_a_draft_cannot_go_straight_to_live():
    """Paper is not optional; it is where the divergence check gets its evidence."""
    with pytest.raises(IllegalTransition):
        lifecycle.check(BotState.DRAFT, BotState.LIVE)


def test_a_stopped_bot_goes_back_through_paper_and_is_told_why():
    with pytest.raises(IllegalTransition) as caught:
        lifecycle.check(BotState.STOPPED, BotState.LIVE)
    assert "paper" in str(caught.value)


def test_the_refusal_names_both_states():
    with pytest.raises(IllegalTransition) as caught:
        lifecycle.check(BotState.DRAFT, BotState.LIVE)
    assert "draft" in str(caught.value)
    assert "live" in str(caught.value)


# --- dry_run follows the state ----------------------------------------------


def test_only_live_routes_for_real():
    bot = make_bot(state=BotState.DRAFT)
    lifecycle.transition(bot, BotState.PAPER)
    assert bot.dry_run is True
    lifecycle.transition(bot, BotState.LIVE)
    assert bot.dry_run is False


def test_stopping_a_live_bot_puts_it_back_into_dry_run():
    bot = make_bot(state=BotState.LIVE)
    bot.dry_run = False
    bot.save()
    lifecycle.transition(bot, BotState.STOPPED)
    assert bot.dry_run is True


def test_a_transition_is_persisted():
    bot = make_bot(state=BotState.DRAFT)
    lifecycle.transition(bot, BotState.PAPER)
    bot.refresh_from_db()
    assert bot.state == BotState.PAPER


def test_a_refused_transition_changes_nothing():
    bot = make_bot(state=BotState.DRAFT)
    with pytest.raises(IllegalTransition):
        lifecycle.transition(bot, BotState.LIVE)
    bot.refresh_from_db()
    assert bot.state == BotState.DRAFT


# --- Q26 retention ----------------------------------------------------------


@pytest.mark.parametrize("interval", ["15m", "1h", "4h", "1d"])
def test_fifteen_minutes_and_above_keeps_every_bar(interval):
    assert retention.keeps_every_bar(interval) is True


@pytest.mark.parametrize("interval", ["1m", "5m"])
def test_the_dense_intervals_are_trimmed(interval):
    assert retention.keeps_every_bar(interval) is False


def test_trimming_a_slow_bot_deletes_nothing():
    bot = make_bot(interval="1h")
    run = make_run(bot)
    _write_bars(run, 10, changed=False, age_days=30)
    assert retention.trim(run) == 0
    assert BotBar.objects.filter(run=run).count() == 10


def test_an_unchanged_bar_outside_the_debug_window_goes():
    bot = make_bot(interval="1m")
    run = make_run(bot)
    _write_bars(run, 5, changed=False, age_days=30)
    assert retention.trim(run) == 5


def test_a_changed_bar_is_kept_however_old():
    """Trimming loses detail, never accountability."""
    bot = make_bot(interval="1m")
    run = make_run(bot)
    _write_bars(run, 5, changed=True, age_days=365)
    assert retention.trim(run) == 0


def test_the_seven_day_window_is_kept_whole():
    bot = make_bot(interval="1m")
    run = make_run(bot)
    _write_bars(run, 5, changed=False, age_days=1)
    assert retention.trim(run) == 0


def test_trimming_twice_deletes_nothing_the_second_time():
    bot = make_bot(interval="1m")
    run = make_run(bot)
    _write_bars(run, 5, changed=False, age_days=30)
    retention.trim(run)
    assert retention.trim(run) == 0


# --- what counts as a change ------------------------------------------------


def test_the_first_bar_is_always_a_change():
    assert retention.is_change(None, {"side": None}, {}) is True


def test_a_side_change_counts():
    assert retention.is_change({"intent": {"side": None}, "plots": {}}, {"side": "long"}, {})


def test_a_stop_level_change_counts():
    previous = {"intent": {"side": "long", "sl_pct": "1"}, "plots": {}}
    assert retention.is_change(previous, {"side": "long", "sl_pct": "2"}, {})


def test_a_plot_value_moving_counts():
    previous = {"intent": {"side": None}, "plots": {"sma": "1"}}
    assert retention.is_change(previous, {"side": None}, {"sma": "2"})


def test_an_identical_bar_does_not_count():
    previous = {"intent": {"side": None, "sl_pct": None, "tp_pct": None}, "plots": {"sma": "1"}}
    same = {"side": None, "sl_pct": None, "tp_pct": None}
    assert retention.is_change(previous, same, {"sma": "1"}) is False


def _write_bars(run, count: int, *, changed: bool, age_days: int) -> None:
    base = int(time.time()) - age_days * 24 * 3600
    BotBar.objects.bulk_create(
        BotBar(
            run=run,
            bar_time=base + index * 60,
            open=D("1"),
            high=D("1"),
            low=D("1"),
            close=D("1"),
            changed=changed,
        )
        for index in range(count)
    )
