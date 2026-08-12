"""Spec §7's emergency halt.

The properties that matter are: flipping it stops *new* routing immediately,
closing an open position still works while it is on, and an environment pin
cannot be cleared through the API.
"""

from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D
from apps.engine.fanout import StopAllActive
from apps.exchanges.base import MarketType, OrderType, Side
from apps.trading import killswitch
from apps.trading.models import KillSwitch
from apps.trading.services import route_close, route_open

KEY = Fernet.generate_key().decode()


def staff_client() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


# --- the switch itself ------------------------------------------------------


@pytest.mark.django_db
def test_defaults_to_running():
    assert killswitch.is_on() is False
    assert killswitch.state()["source"] == "off"


@pytest.mark.django_db
def test_runtime_flip_is_visible_immediately():
    killswitch.set_stop_all(True, actor="boss", reason="exchange outage")
    assert killswitch.is_on() is True

    state = killswitch.state()
    assert state["source"] == "panel"
    assert state["reason"] == "exchange outage"
    assert state["updated_by"] == "boss"


@pytest.mark.django_db
@override_settings(TRADING={**settings.TRADING, "STOP_ALL": True})
def test_environment_pin_cannot_be_cleared():
    assert killswitch.is_on() is True
    assert killswitch.state()["locked"] is True

    with pytest.raises(PermissionError):
        killswitch.set_stop_all(False, actor="boss")


@pytest.mark.django_db
def test_unreadable_switch_fails_halted(monkeypatch):
    """When we cannot tell, we stop. Routing partner capital is the wrong default."""
    from django.db import DatabaseError

    def explode():
        raise DatabaseError("no database")

    monkeypatch.setattr(killswitch, "_row", explode)
    assert killswitch.runtime_on() is True


# --- the endpoint -----------------------------------------------------------


@pytest.mark.django_db
def test_endpoint_requires_staff():
    User.objects.create_user("partner", password="pw12345!")
    client = Client()
    assert client.login(username="partner", password="pw12345!")
    body, kind = {"on": True}, "application/json"
    assert client.post("/api/trading/stop-all/", body, content_type=kind).status_code == 403
    anonymous = Client().post("/api/trading/stop-all/", body, content_type=kind)
    assert anonymous.status_code in (401, 403)


@pytest.mark.django_db
def test_endpoint_toggles_and_policy_reports_it():
    client = staff_client()

    response = client.post("/api/trading/stop-all/", {"on": True}, content_type="application/json")
    assert response.status_code == 200
    assert response.json()["stop_all"] is True
    assert KillSwitch.objects.get(singleton=1).stop_all is True

    assert client.get("/api/trading/policy/").json()["stop_all"] is True

    client.post("/api/trading/stop-all/", {"on": False}, content_type="application/json")
    assert client.get("/api/trading/policy/").json()["stop_all"] is False


@pytest.mark.django_db
def test_endpoint_rejects_a_non_boolean():
    response = staff_client().post(
        "/api/trading/stop-all/", {"on": "yes"}, content_type="application/json"
    )
    assert response.status_code == 400


# --- effect on routing ------------------------------------------------------


@sync_to_async
def make_account(label: str):
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D("1000"),
        last_balance_asset="USDT",
    )


async def open_a_trade():
    return await route_open(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.5"),
        tp_pct=D("1"),
        limit_price=D("100000"),
    )


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_halt_blocks_new_routing_but_not_closing():
    await make_account("partner-a")
    trade, result = await open_a_trade()
    assert result.all_ok

    await sync_to_async(killswitch.set_stop_all)(True, actor="boss")

    with pytest.raises(StopAllActive):
        await open_a_trade()

    # The escape hatch: an open position can still be closed while halted.
    close = await route_close(trade=trade)
    assert close.all_ok
