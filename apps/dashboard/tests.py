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
    assert "equity_series" not in data["runs"][0]


@pytest.mark.django_db
def test_analytics_monthly_and_by_asset(client):
    user = _login(client)
    strat = Strategy.objects.create(user=user, name="a", type="pine", symbol="BTC")
    Backtest.objects.create(
        strategy=strat,
        symbol="BTC",
        status=Backtest.Status.DONE,
        metrics={"net_pnl": 50, "num_trades": 4, "win_rate": 0.5, "funding_paid": 1.5},
    )
    Backtest.objects.create(
        strategy=strat,
        symbol="ETH",
        status=Backtest.Status.DONE,
        metrics={"net_pnl": -10, "num_trades": 2, "win_rate": 0.0, "funding_paid": 0.5},
    )
    data = client.get("/api/analytics/").json()
    assert data["count"] == 2
    assert len(data["monthly"]) >= 1
    assert sum(b["net_pnl"] for b in data["by_asset"]) == pytest.approx(40.0)
    assert data["total_funding_paid"] == pytest.approx(2.0)
    symbols = {b["symbol"] for b in data["by_asset"]}
    assert symbols == {"BTC", "ETH"}


@pytest.mark.django_db
def test_analytics_excludes_non_done(client):
    user = _login(client)
    strat = Strategy.objects.create(user=user, name="a", type="pine", symbol="BTC")
    Backtest.objects.create(strategy=strat, symbol="BTC", status=Backtest.Status.PENDING, metrics={})
    Backtest.objects.create(strategy=strat, symbol="BTC", status=Backtest.Status.FAILED, metrics={})
    data = client.get("/api/analytics/").json()
    assert data["count"] == 0
    assert data["runs"] == []


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
