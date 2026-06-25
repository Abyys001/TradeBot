"""Tests for dashboard API (overview, analytics, kill-switch)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.execution.models import OrderRecord
from apps.strategies.models import Strategy, StrategyState
from apps.transpiler.models import Backtest


def _login(client, username="dash"):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="pw")
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_overview_counts(client):
    user = _login(client)
    Strategy.objects.create(user=user, name="a", type="pine", symbol="BTC", status=Strategy.Status.ACTIVE)
    s2 = Strategy.objects.create(user=user, name="b", type="pine", symbol="ETH", status=Strategy.Status.DRAFT)
    StrategyState.objects.create(strategy=s2, pnl=Decimal("12.5"))
    OrderRecord.objects.create(strategy=s2, symbol="ETH", side="buy", order_type="market", size=Decimal("1"))

    data = client.get("/api/overview/").json()
    assert data["strategies"]["total"] == 2
    assert data["strategies"]["active"] == 1
    assert data["orders"]["total"] == 1
    assert data["pnl"]["total_unrealized"] == "12.50000000"


@pytest.mark.django_db
def test_overview_scoped_to_user(client):
    _login(client, "owner")
    User = get_user_model()
    other = User.objects.create_user(username="intruder", password="pw")
    Strategy.objects.create(user=other, name="x", type="pine", symbol="BTC")
    data = client.get("/api/overview/").json()
    assert data["strategies"]["total"] == 0


@pytest.mark.django_db
def test_analytics_best_worst(client):
    user = _login(client)
    strat = Strategy.objects.create(user=user, name="a", type="pine", symbol="BTC")
    Backtest.objects.create(strategy=strat, symbol="BTC", status=Backtest.Status.DONE, metrics={"net_pnl": 100})
    Backtest.objects.create(strategy=strat, symbol="BTC", status=Backtest.Status.DONE, metrics={"net_pnl": -50})
    data = client.get("/api/analytics/").json()
    assert data["count"] == 2
    assert data["best"]["net_pnl"] == 100
    assert data["worst"]["net_pnl"] == -50


@pytest.mark.django_db
def test_kill_switch_toggles_flag(client):
    user = _login(client)
    assert user.is_trading_enabled is False
    resp = client.post("/api/me/kill-switch/", {"enabled": True}, content_type="application/json")
    assert resp.json()["is_trading_enabled"] is True
    user.refresh_from_db()
    assert user.is_trading_enabled is True


@pytest.mark.django_db
def test_overview_requires_auth(client):
    resp = client.get("/api/overview/")
    assert resp.status_code in (401, 403)
