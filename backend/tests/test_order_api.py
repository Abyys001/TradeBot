"""The routing endpoints over HTTP — the surface the panel actually calls.

`test_services` exercises `route_open` directly, which skips everything between
the browser and it: the auth gate, the CSRF check, and the input parsing. That
is the half where a bad number becomes an order. These are plain Django *async*
views rather than DRF ones (DRF 3.15 cannot host an async view without
serialising the fan-out through a worker thread), so none of DRF's request
validation or permission machinery applies to them — every guard here is one
this module has to own, and therefore one worth pinning.

What these pin:

  - only a signed-in staff user can move money, and a cross-site POST cannot;
  - a malformed pair, a negative stop, or a zero limit price is refused here
    rather than dispatched to eight exchanges to fail eight different ways;
  - the fan-out reaches every account and reports inside the §4 budget.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D

pytestmark = pytest.mark.django_db(transaction=True)

KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _encryption_key():
    """Building a paper adapter still goes through the credential vault."""
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield

OPEN = "/api/trading/orders/open/"


def account(label: str, *, balance: str = "1000") -> ConnectedAccount:
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D(balance),
        last_balance_asset="USDT",
    )


def staff_client(**kwargs) -> Client:
    User.objects.create_user("boss", password="pw", is_staff=True)
    client = Client(**kwargs)
    client.login(username="boss", password="pw")
    return client


def order(**overrides) -> dict:
    """A valid market order. Carries a limit price so nothing needs a feed."""
    return {
        "symbol": "BTCUSDT",
        "side": "long",
        "market": "futures",
        "order_type": "market",
        "leverage": 10,
        "sl_pct": "0.5",
        "tp_pct": "1",
        "limit_price": "100000",
        **overrides,
    }


def post(client: Client, body: dict, **extra):
    return client.post(OPEN, body, content_type="application/json", **extra)


# --- who may route ----------------------------------------------------------


def test_an_anonymous_caller_cannot_route():
    assert Client().post(OPEN, order(), content_type="application/json").status_code == 401


def test_a_signed_in_non_staff_user_cannot_route():
    User.objects.create_user("watcher", password="pw")
    client = Client()
    client.login(username="watcher", password="pw")
    assert post(client, order()).status_code == 403


def test_a_cross_site_post_cannot_route():
    """Being logged in is not enough — the request must come from the panel.

    These views are `csrf_exempt` no longer. They were, because CSRF was the
    obvious casualty of hand-rolling async views, and the result was an
    endpoint that fans a leveraged entry across every connected account on any
    POST carrying the admin's session cookie. SameSite=Lax happens to block
    that in a current browser; a money endpoint should not be relying on a
    cookie default it does not set for its only line of defence.
    """
    account("partner")
    client = staff_client(enforce_csrf_checks=True)
    assert post(client, order()).status_code == 403


def test_the_panels_own_post_routes():
    account("partner")
    client = staff_client(enforce_csrf_checks=True)
    client.get("/api/accounts/auth/csrf/")
    response = post(client, order(), HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 200, response.content


# --- what a leg is allowed to be built from ---------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", ""),
        ("symbol", "BTC/USDT"),
        ("symbol", "../../etc/passwd"),
        # Sizing divides by this price.
        ("limit_price", "0"),
        ("limit_price", "-100"),
        # A negative stop sits on the profit side of entry and fires the moment
        # the trade goes right; past 100% it is a price below zero.
        ("sl_pct", "0"),
        ("sl_pct", "-5"),
        ("sl_pct", "150"),
        ("tp_pct", "-1"),
        ("leverage", 0),
        ("leverage", 999),
        ("leverage", "ten"),
        ("side", "sideways"),
        ("market", "options"),
    ],
)
def test_a_typo_is_refused_before_it_becomes_an_order(field, value):
    account("partner")
    client = staff_client()
    assert post(client, order(**{field: value})).status_code == 400


def test_a_generous_take_profit_is_not_a_typo():
    """No ceiling on the upside — a 250% target is a real thing to ask for."""
    account("partner")
    client = staff_client()
    assert post(client, order(tp_pct="250")).status_code == 200


def test_a_lowercase_pair_is_normalised_rather_than_refused():
    account("partner")
    client = staff_client()
    response = post(client, order(symbol="btcusdt"))
    assert response.status_code == 200
    assert response.json()["succeeded"]


def test_a_limit_order_without_a_price_is_refused():
    account("partner")
    client = staff_client()
    body = order(order_type="limit")
    body.pop("limit_price")
    assert post(client, body).status_code == 400


# --- the fan-out itself -----------------------------------------------------


def test_every_account_is_reached_inside_the_budget():
    """Spec §4: N accounts, concurrently, reported within one second.

    The assertion that matters is `within_budget` — it is computed from the
    fan-out's own wall clock, so it is the same number the panel shows and the
    same one the spec caps.
    """
    for i in range(5):
        account(f"partner-{i}", balance=str(1000 * (i + 1)))

    client = staff_client()
    body = post(client, order()).json()

    assert len(body["succeeded"]) == 5
    assert body["failed"] == []
    assert body["within_budget"] is True


def test_an_account_already_in_a_trade_is_left_out_not_refused():
    """Spec §5: one open trade per account, and one busy account is not a veto."""
    account("busy")
    client = staff_client()
    assert len(post(client, order()).json()["succeeded"]) == 1

    account("fresh")
    second = post(client, order()).json()
    assert len(second["succeeded"]) == 1
