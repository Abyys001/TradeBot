"""Every money-moving endpoint must refuse anonymous callers.

This exists because an earlier revision shipped the routing endpoints with no
authentication at all — anything that could reach the API could have opened or
closed positions across every connected account.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import AsyncClient, Client

MONEY_ENDPOINTS = [
    "/api/trading/orders/open/",
    "/api/trading/orders/1/amend/",
    "/api/trading/orders/1/close/",
    "/api/trading/balances/refresh/",
]


@pytest.mark.django_db
@pytest.mark.parametrize("path", MONEY_ENDPOINTS)
def test_routing_endpoints_reject_anonymous_callers(path):
    response = Client().post(path, data="{}", content_type="application/json")
    assert response.status_code == 401, f"{path} is reachable without logging in"


@pytest.mark.django_db
@pytest.mark.parametrize("path", MONEY_ENDPOINTS)
def test_routing_endpoints_reject_non_staff_users(path):
    User.objects.create_user("partner", password="pw12345!")
    client = Client()
    assert client.login(username="partner", password="pw12345!")
    response = client.post(path, data="{}", content_type="application/json")
    assert response.status_code == 403, f"{path} is reachable by a non-staff user"


@pytest.mark.django_db
def test_account_and_config_endpoints_require_authentication():
    client = Client()
    for path in (
        "/api/accounts/accounts/",
        "/api/accounts/notifications/",
        "/api/trading/policy/",
        "/api/trading/exchanges/",
        "/api/trading/trades/",
    ):
        assert client.get(path).status_code in (401, 403), f"{path} is public"


@pytest.mark.django_db
def test_risk_preview_is_deliberately_public():
    """A pure calculator over supplied numbers — it reads no account data."""
    response = Client().post(
        "/api/trading/risk-preview/",
        data=json.dumps({"balance": "1000", "leverage": 10, "entry": "100000", "sl_pct": "2"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["readings"]["price"]["loss_at_stop"] == "198"


@pytest.mark.django_db
def test_login_rejects_a_non_staff_user():
    User.objects.create_user("partner", password="pw12345!")
    response = Client().post(
        "/api/accounts/auth/login/",
        data=json.dumps({"username": "partner", "password": "pw12345!"}),
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_login_does_not_reveal_which_half_was_wrong():
    User.objects.create_superuser("admin", password="pw12345!")
    client = Client()
    wrong_user = client.post(
        "/api/accounts/auth/login/",
        data=json.dumps({"username": "nobody", "password": "pw12345!"}),
        content_type="application/json",
    )
    wrong_password = client.post(
        "/api/accounts/auth/login/",
        data=json.dumps({"username": "admin", "password": "wrong"}),
        content_type="application/json",
    )
    assert wrong_user.status_code == wrong_password.status_code == 401
    assert wrong_user.json()["detail"] == wrong_password.json()["detail"]


@pytest.mark.django_db
def test_a_staff_user_can_log_in_and_reach_the_panel():
    User.objects.create_superuser("admin", password="pw12345!")
    client = Client()
    response = client.post(
        "/api/accounts/auth/login/",
        data=json.dumps({"username": "admin", "password": "pw12345!"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["is_staff"] is True
    assert client.get("/api/trading/policy/").status_code == 200


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_staff_user_can_route_an_order():
    from asgiref.sync import sync_to_async

    from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
    from apps.core.money import D

    await sync_to_async(User.objects.create_superuser)("admin", password="pw12345!")
    await sync_to_async(ConnectedAccount.objects.create)(
        label="demo",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D("1000"),
        last_balance_asset="USDT",
    )
    client = AsyncClient()
    assert await sync_to_async(client.login)(username="admin", password="pw12345!")

    response = await client.post(
        "/api/trading/orders/open/",
        data=json.dumps({"symbol": "BTCUSDT", "side": "long", "leverage": 5}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert len(response.json()["succeeded"]) == 1
