"""P2 gate: a SUSPECT/MISSING bar halts the runner AND applies the §4.3 position policy.

These exercise the wiring added in `runner._halt_if_suspect` — that the halt decision
(`halt_policy.evaluate_halt`) is computed, logged to `ExecutionLog` as `bar.halt`, and
that a FLATTEN decision actually calls the Tabdeal broker's close. Unit-level: calls the
runner method directly, no stream/session machinery. Uses LocMemCache (dev_sqlite).
"""
from unittest.mock import patch

import pytest

from apps.accounts.models import User
from apps.credentials.models import Exchange, ExchangeCredential
from apps.exchange.halt_policy import FailureClass
from apps.execution.models import ExecutionLog
from apps.strategies.models import Strategy, StrategyState

from .runner import LiveIncrementalRunner, _halt_bars_key


def _tabdeal_strategy():
    user = User.objects.create_user(username="haltowner", password="x", is_trading_enabled=True)
    cred = ExchangeCredential(user=user, exchange=Exchange.TABDEAL, label="td", is_active=True)
    cred.set_api_credentials("key", "secret")
    cred.save()
    strat = Strategy.objects.create(
        user=user, credential=cred, name="halt", symbol="BTC", timeframe="1m",
        warmup_bars=10, source="//x", validation_status="ok",
    )
    state, _ = StrategyState.objects.get_or_create(strategy=strat)
    return strat, state


def _candle(ts, quality):
    return {"ts": ts, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "quality": quality}


@pytest.mark.django_db
def test_suspect_naked_position_flattens():
    from django.core.cache import cache

    strat, state = _tabdeal_strategy()
    cache.delete(_halt_bars_key(strat.pk))
    runner = LiveIncrementalRunner()

    with (
        patch.object(LiveIncrementalRunner, "_classify_failure", return_value=FailureClass.COMPUTE_GAP),
        patch("apps.transpiler.runtime.tabdeal_live_broker.TabdealLiveBroker") as MockBroker,
    ):
        MockBroker.return_value.close.return_value = object()
        skipped = runner._halt_if_suspect(strat, state, _candle(1000, "SUSPECT"))

    assert skipped is True  # bar never reaches the interpreter (invariant 1)
    halt = ExecutionLog.objects.filter(strategy=strat, event="bar.halt").latest("id")
    assert halt.payload["action"] == "flatten"
    assert halt.payload["reason"] == "naked_position"
    assert halt.payload["failure_class"] == FailureClass.COMPUTE_GAP.value
    MockBroker.return_value.close.assert_called_once()
    assert ExecutionLog.objects.filter(strategy=strat, event="bar.halt_flatten").exists()


@pytest.mark.django_db
def test_suspect_sl_confirmed_holds():
    from django.core.cache import cache

    strat, state = _tabdeal_strategy()
    cache.delete(_halt_bars_key(strat.pk))
    state.sl_confirmed = True  # in-memory (field lands in P6); getattr fallback picks it up
    runner = LiveIncrementalRunner()

    with (
        patch.object(LiveIncrementalRunner, "_classify_failure", return_value=FailureClass.COMPUTE_GAP),
        patch("apps.transpiler.runtime.tabdeal_live_broker.TabdealLiveBroker") as MockBroker,
    ):
        skipped = runner._halt_if_suspect(strat, state, _candle(2000, "SUSPECT"))

    assert skipped is True
    halt = ExecutionLog.objects.filter(strategy=strat, event="bar.halt").latest("id")
    assert halt.payload["action"] == "hold"
    MockBroker.assert_not_called()  # a protected, in-budget position is held, not flattened
    assert not ExecutionLog.objects.filter(strategy=strat, event="bar.halt_flatten").exists()


@pytest.mark.django_db
def test_missing_bar_always_flattens_even_with_sl():
    from django.core.cache import cache

    strat, state = _tabdeal_strategy()
    cache.delete(_halt_bars_key(strat.pk))
    state.sl_confirmed = True
    runner = LiveIncrementalRunner()

    with (
        patch.object(LiveIncrementalRunner, "_classify_failure", return_value=FailureClass.COMPUTE_GAP),
        patch("apps.transpiler.runtime.tabdeal_live_broker.TabdealLiveBroker") as MockBroker,
    ):
        MockBroker.return_value.close.return_value = object()
        skipped = runner._halt_if_suspect(strat, state, _candle(3000, "MISSING"))

    assert skipped is True
    halt = ExecutionLog.objects.filter(strategy=strat, event="bar.halt").latest("id")
    assert halt.payload["action"] == "flatten"
    assert halt.payload["reason"] == "bar_missing"
    MockBroker.return_value.close.assert_called_once()


@pytest.mark.django_db
def test_blind_hold_budget_exceeded_flattens():
    """After max_blind_hold protected bars, a SUSPECT bar flattens (§4.3)."""
    from django.core.cache import cache

    strat, state = _tabdeal_strategy()
    state.sl_confirmed = True
    cache.set(_halt_bars_key(strat.pk), 3)  # already at default max_blind_hold
    runner = LiveIncrementalRunner()

    with (
        patch.object(LiveIncrementalRunner, "_classify_failure", return_value=FailureClass.COMPUTE_GAP),
        patch("apps.transpiler.runtime.tabdeal_live_broker.TabdealLiveBroker") as MockBroker,
    ):
        MockBroker.return_value.close.return_value = object()
        runner._halt_if_suspect(strat, state, _candle(4000, "SUSPECT"))

    halt = ExecutionLog.objects.filter(strategy=strat, event="bar.halt").latest("id")
    assert halt.payload["action"] == "flatten"
    assert halt.payload["reason"] == "exceeded_max_blind_hold"
    MockBroker.return_value.close.assert_called_once()
