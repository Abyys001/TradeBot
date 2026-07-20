"""Tests for watchdog monitor — execute() exchange calls and guardian integration."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.models import User
from apps.credentials.models import Exchange, ExchangeCredential
from apps.strategies.models import Strategy, StrategyState
from apps.watchdog.guardian import GuardianCheck, PositionState
from apps.watchdog.models import WatchdogAction, WatchdogConfig
from apps.watchdog.monitor import WatchdogMonitor


def _make_user(trading=True):
    return User.objects.create_user(
        username="owner", password="x", role=User.Role.ADMIN, is_trading_enabled=trading,
    )


def _make_strategy(user, *, global_stop_loss_pct=None):
    cred = ExchangeCredential(user=user, exchange=Exchange.TABDEAL, label="td", is_active=True)
    cred.set_api_credentials("key", "secret")
    cred.save()
    risk: dict = {}
    if global_stop_loss_pct is not None:
        risk["global_stop_loss_pct"] = global_stop_loss_pct
    strat = Strategy.objects.create(
        user=user,
        credential=cred,
        name="watchdog-test",
        symbol="BTC",
        source="//x",
        validation_status="ok",
        live_config={"risk": risk},
    )
    StrategyState.objects.create(strategy=strat)
    return strat, cred


def _fake_client():
    client = MagicMock()
    client.get_position.return_value = None
    client.get_open_position_id.return_value = 42
    client.close_position.return_value = {"avgPrice": "100.0"}
    client.set_position_sl_tp.return_value = {}
    return client


def _monitor(strategy, client):
    return WatchdogMonitor(strategy.pk, client)


# ----- guardian integration in check() -----


@pytest.mark.django_db
def test_check_uses_guardian_for_sl_status():
    """check() calls the guardian and uses its has_sl for tier evaluation."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client()

    guardian_result = GuardianCheck(
        ok=True,
        position=PositionState(
            symbol="BTC", side="LONG", size=0.1, entry_price=50000,
            has_sl=True, has_tp=False, pnl=10.0, updated_at=1.0,
        ),
    )

    # Mock heartbeat to return a recent timestamp so gap is between t_self (5s) and t_dead (15s)
    now = time.time()
    recent_heartbeat = now - 8  # 8s gap → Tier 1

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), \
         patch("apps.watchdog.monitor.WatchdogMonitor._run_guardian", return_value=guardian_result):
        monitor = _monitor(strat, client)
        with patch("apps.watchdog.monitor.WatchdogMonitor._read_heartbeat", return_value=recent_heartbeat):
            tier, detail = monitor.check()

    # 8s gap >= t_self (5s) but < t_dead (15s), SL confirmed → Tier 1 "monitor"
    assert tier == 1
    assert detail["sl_confirmed"] is True
    assert detail["action"] == "monitor"


@pytest.mark.django_db
def test_check_guardian_failure_falls_back():
    """If guardian throws, check() still works with sl_confirmed=False."""
    user = _make_user()
    strat, _cred = _make_strategy(user)

    now = time.time()
    recent_heartbeat = now - 8  # 8s gap → Tier 1

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient") as mock_cls, \
         patch("apps.watchdog.monitor.WatchdogMonitor._run_guardian", side_effect=ConnectionError("timeout")):
        client = _fake_client()
        mock_cls.return_value = client
        monitor = _monitor(strat, client)
        with patch("apps.watchdog.monitor.WatchdogMonitor._read_heartbeat", return_value=recent_heartbeat):
            tier, detail = monitor.check()

    # Guardian failed → sl_confirmed=False → Tier 1 attach_sl
    assert detail["sl_confirmed"] is False
    assert detail["action"] == "attach_sl"


@pytest.mark.django_db
def test_check_guardian_sets_sl_confirmed_from_position():
    """Guardian position.has_sl updates state.sl_confirmed."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client()

    guardian_result = GuardianCheck(
        ok=True,
        position=PositionState(
            symbol="BTC", side="LONG", size=0.1, entry_price=50000,
            has_sl=True, has_tp=False, pnl=10.0, updated_at=1.0,
        ),
    )

    now = time.time()
    recent_heartbeat = now - 8

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), \
         patch("apps.watchdog.monitor.WatchdogMonitor._run_guardian", return_value=guardian_result):
        monitor = _monitor(strat, client)
        with patch("apps.watchdog.monitor.WatchdogMonitor._read_heartbeat", return_value=recent_heartbeat):
            tier, detail = monitor.check()

    assert monitor.state.sl_confirmed is True


# ----- execute: attach SL -----


@pytest.mark.django_db
def test_execute_attach_sl_calls_exchange():
    """Tier 1 attach_sl calls set_position_sl_tp with computed price."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client()

    guardian_result = GuardianCheck(
        ok=True,
        position=PositionState(
            symbol="BTC", side="LONG", size=0.1, entry_price=50000,
            has_sl=False, has_tp=False, pnl=0, updated_at=1.0,
        ),
    )

    _attach_detail = {
        "action": "attach_sl", "reason": "slow_no_sl",
        "sl_confirmed": False, "should_attach_sl": True,
        "should_flatten": False, "should_kill_switch": False,
    }

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.state.guardian = guardian_result
        monitor.execute(1, _attach_detail)

    # Long @ 50000, 10% SL → 45000
    client.set_position_sl_tp.assert_called_once_with(
        position_id=42, sl_price=45000.0, symbol="BTC",
    )
    assert WatchdogAction.objects.filter(
        strategy_id=strat.pk, action_type=WatchdogAction.ActionType.SL_ATTACHED,
    ).exists()


@pytest.mark.django_db
def test_execute_attach_sl_short_position():
    """SL for short position is above entry."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=5)
    client = _fake_client()

    guardian_result = GuardianCheck(
        ok=True,
        position=PositionState(
            symbol="BTC", side="SHORT", size=0.5, entry_price=100,
            has_sl=False, has_tp=False, pnl=0, updated_at=1.0,
        ),
    )

    _attach_detail = {
        "action": "attach_sl", "reason": "slow_no_sl",
        "sl_confirmed": False, "should_attach_sl": True,
        "should_flatten": False, "should_kill_switch": False,
    }

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.state.guardian = guardian_result
        monitor.execute(1, _attach_detail)

    # Short @ 100, 5% SL → 105.0
    client.set_position_sl_tp.assert_called_once_with(
        position_id=42, sl_price=105.0, symbol="BTC",
    )


@pytest.mark.django_db
def test_execute_attach_sl_exchange_error():
    """Exchange error during SL attach is logged, not raised."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client()
    client.set_position_sl_tp.side_effect = Exception("API timeout")

    guardian_result = GuardianCheck(
        ok=True,
        position=PositionState(
            symbol="BTC", side="LONG", size=0.1, entry_price=50000,
            has_sl=False, has_tp=False, pnl=0, updated_at=1.0,
        ),
    )

    _attach_detail = {
        "action": "attach_sl", "reason": "slow_no_sl",
        "sl_confirmed": False, "should_attach_sl": True,
        "should_flatten": False, "should_kill_switch": False,
    }

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.state.guardian = guardian_result
        monitor.execute(1, _attach_detail)

    action = WatchdogAction.objects.get(strategy_id=strat.pk, action_type=WatchdogAction.ActionType.SL_ATTACHED)
    assert "API timeout" in action.detail.get("error", "")


@pytest.mark.django_db
def test_execute_attach_sl_no_position():
    """If no position exists, attach_sl logs and returns."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client()
    client.get_position.return_value = None

    _attach_detail = {
        "action": "attach_sl", "reason": "slow_no_sl",
        "sl_confirmed": False, "should_attach_sl": True,
        "should_flatten": False, "should_kill_switch": False,
    }

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.state.guardian = GuardianCheck(ok=True, position=None)
        monitor.execute(1, _attach_detail)

    client.set_position_sl_tp.assert_not_called()


# ----- execute: flatten -----


@pytest.mark.django_db
def test_execute_flatten_calls_close_position():
    """Tier 2 flatten calls close_position on the exchange."""
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client()

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.execute(2, {
            "action": "flatten_naked",
            "reason": "dead_no_sl",
            "should_flatten": True,
        })

    client.close_position.assert_called_once_with("BTC")
    assert WatchdogAction.objects.filter(
        strategy_id=strat.pk, action_type=WatchdogAction.ActionType.POSITION_FLAT,
    ).exists()


@pytest.mark.django_db
def test_execute_flatten_exchange_error():
    """Exchange error during flatten is logged, not raised."""
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client()
    client.close_position.side_effect = Exception("network error")

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.execute(2, {
            "action": "flatten_naked",
            "reason": "dead_no_sl",
            "should_flatten": True,
        })

    action = WatchdogAction.objects.get(strategy_id=strat.pk, action_type=WatchdogAction.ActionType.POSITION_FLAT)
    assert "network error" in action.detail.get("error", "")


# ----- execute: kill switch -----


@pytest.mark.django_db
def test_execute_kill_switch_flattens_and_disables_trading():
    """Tier 3 flattens position and disables user trading."""
    user = _make_user(trading=True)
    strat, _cred = _make_strategy(user)
    client = _fake_client()

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.execute(3, {
            "action": "kill_switch",
            "reason": "daily_loss_breach",
            "should_flatten": True,
            "should_kill_switch": True,
        })

    client.close_position.assert_called_once_with("BTC")

    user.refresh_from_db()
    assert user.is_trading_enabled is False

    assert WatchdogAction.objects.filter(
        strategy_id=strat.pk, action_type=WatchdogAction.ActionType.KILL_SWITCH,
    ).exists()


@pytest.mark.django_db
def test_execute_kill_switch_already_disabled():
    """Kill switch is idempotent — no error if already disabled."""
    user = _make_user(trading=False)
    strat, _cred = _make_strategy(user)
    client = _fake_client()

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.execute(3, {
            "action": "kill_switch",
            "reason": "daily_loss_breach",
            "should_flatten": True,
            "should_kill_switch": True,
        })

    client.close_position.assert_called_once()
    user.refresh_from_db()
    assert user.is_trading_enabled is False


# ----- healthy recovery -----


@pytest.mark.django_db
def test_execute_healthy_logs_recovery():
    """Transition from degraded → healthy logs heartbeat recovery."""
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client()

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.state.current_tier = 2
        monitor.execute(0, {"action": "healthy"})

    assert WatchdogAction.objects.filter(
        strategy_id=strat.pk, action_type=WatchdogAction.ActionType.HEARTBEAT_RECOVER,
    ).exists()


@pytest.mark.django_db
def test_execute_healthy_no_log_if_was_healthy():
    """If already healthy, no recovery log."""
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client()

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.state.current_tier = 0
        monitor.execute(0, {"action": "healthy"})

    assert not WatchdogAction.objects.filter(
        strategy_id=strat.pk, action_type=WatchdogAction.ActionType.HEARTBEAT_RECOVER,
    ).exists()


# ----- disabled -----


@pytest.mark.django_db
def test_execute_disabled_noop():
    """Disabled action does nothing."""
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client()

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        monitor = _monitor(strat, client)
        monitor.execute(0, {"action": "disabled"})

    client.close_position.assert_not_called()
    client.set_position_sl_tp.assert_not_called()
