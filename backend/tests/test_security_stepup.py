"""`docs/security-plan.md` §2 A6 — asking for the password again, and where not to.

Step-up guards three things: **credentials, money records, and promoting a bot
to live**. The tests that matter most here are the negative ones — that it does
not stand in front of opening, amending or closing a position, or in front of
the halt. That exclusion is the design, so it is pinned rather than assumed.
"""

from __future__ import annotations

import time

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D
from apps.security import flags, stepup
from apps.security.models import SecurityEvent, SecurityEventKind, SecurityPolicy

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()
PASSWORD = "pw12345!"

ACCOUNTS = "/api/accounts/accounts/"
LEDGER = "/api/accounts/ledger/"
STEP_UP = "/api/security/step-up/"
SECURITY_POLICY = "/api/security/policy/"
STOP_ALL = "/api/trading/stop-all/"
OPEN = "/api/trading/orders/open/"


@pytest.fixture(autouse=True)
def _encryption_key():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def arm(**switches) -> None:
    SecurityPolicy.objects.update_or_create(pk=1, defaults=switches)
    flags.invalidate()


def staff_client(username: str = "boss") -> Client:
    User.objects.create_user(username, password=PASSWORD, is_staff=True)
    client = Client()
    assert client.login(username=username, password=PASSWORD)
    return client


def account(label: str = "one") -> ConnectedAccount:
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D("1000"),
        last_balance_asset="USDT",
    )


def new_account_body() -> dict:
    return {
        "label": "second",
        "exchange": Exchange.PAPER,
        "status": AccountStatus.ACTIVE,
        "api_key": "k",
        "api_secret": "s",
    }


def confirm(client: Client, password: str = PASSWORD):
    return client.post(STEP_UP, {"password": password}, content_type="application/json")


# --------------------------------------------------------------------------
# Off changes nothing
# --------------------------------------------------------------------------


def test_with_the_switch_off_nothing_is_ever_asked_for():
    client = staff_client()
    arm(step_up=False)

    assert client.get(STEP_UP).json() == {"required": False, "seconds_left": 0}
    assert client.post(ACCOUNTS, new_account_body()).status_code == 201


def test_reads_are_never_guarded_even_with_the_switch_on():
    account()
    client = staff_client()
    arm(step_up=True)

    assert client.get(ACCOUNTS).status_code == 200
    assert client.get(LEDGER).status_code == 200


# --------------------------------------------------------------------------
# What it does guard
# --------------------------------------------------------------------------


def test_a_credential_write_is_refused_until_the_password_is_confirmed():
    client = staff_client()
    arm(step_up=True)

    refused = client.post(ACCOUNTS, new_account_body())
    assert refused.status_code == 403
    assert refused.json()["code"] == "step_up_required"
    assert refused.json()["action"] == "connected_account"

    assert confirm(client).status_code == 200
    assert client.post(ACCOUNTS, new_account_body()).status_code == 201


def test_deleting_an_account_is_guarded_too():
    existing = account()
    client = staff_client()
    arm(step_up=True)

    assert client.delete(f"{ACCOUNTS}{existing.pk}/").status_code == 403
    confirm(client)
    assert client.delete(f"{ACCOUNTS}{existing.pk}/").status_code in (200, 204)


def test_changing_the_switches_themselves_is_guarded():
    client = staff_client()
    arm(step_up=True)

    refused = client.post(SECURITY_POLICY, {"audit_log": True},
                          content_type="application/json")
    assert refused.status_code == 403
    assert refused.json()["code"] == "step_up_required"

    confirm(client)
    assert client.post(SECURITY_POLICY, {"audit_log": True},
                       content_type="application/json").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_putting_a_bot_live_is_guarded_and_starting_it_on_paper_is_not():
    from apps.bots.models import BotState
    from tests.bot_factory import make_bot

    client = staff_client()
    bot = make_bot(state=BotState.DRAFT)
    arm(step_up=True)

    live = client.post(f"/api/bots/bots/{bot.pk}/start/", {"state": BotState.LIVE},
                       content_type="application/json")
    assert live.status_code == 403
    assert live.json()["code"] == "step_up_required"
    assert live.json()["action"] == "bot_live"

    paper = client.post(f"/api/bots/bots/{bot.pk}/start/", {"state": BotState.PAPER},
                        content_type="application/json")
    assert paper.status_code != 403


# --------------------------------------------------------------------------
# What it must never guard
# --------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_routing_a_position_is_never_guarded():
    """A password prompt in front of "close this position" costs money during
    the one minute it matters most."""
    account()
    client = staff_client()
    arm(step_up=True)

    opened = client.post(
        OPEN,
        {
            "symbol": "BTCUSDT", "side": "long", "market": "futures",
            "order_type": "market", "leverage": 10, "sl_pct": "0.5",
            "tp_pct": "1", "limit_price": "100000",
        },
        content_type="application/json",
    )
    assert opened.status_code == 200, opened.content

    trade_id = opened.json()["trade_id"]
    assert client.post(f"/api/trading/orders/{trade_id}/close/",
                       content_type="application/json").status_code == 200


def test_the_halt_is_never_guarded():
    client = staff_client()
    arm(step_up=True)

    halted = client.post(STOP_ALL, {"on": True}, content_type="application/json")
    assert halted.status_code == 200


# --------------------------------------------------------------------------
# The grant
# --------------------------------------------------------------------------


def test_the_grant_belongs_to_one_browser_and_expires():
    User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    here, there = Client(), Client()
    assert here.login(username="boss", password=PASSWORD)
    assert there.login(username="boss", password=PASSWORD)
    arm(step_up=True, step_up_grace_seconds=300)

    confirm(here)
    assert here.get(STEP_UP).json()["seconds_left"] > 0
    assert there.get(STEP_UP).json()["seconds_left"] == 0
    assert there.post(ACCOUNTS, new_account_body()).status_code == 403

    session = here.session
    session[stepup.SESSION_KEY] = time.time() - 301
    session.save()
    assert here.get(STEP_UP).json()["seconds_left"] == 0
    assert here.post(ACCOUNTS, new_account_body()).status_code == 403


def test_the_wrong_password_grants_nothing_and_is_recorded():
    client = staff_client()
    arm(step_up=True, audit_log=True)

    refused = confirm(client, "not-the-password")

    assert refused.status_code == 401
    assert client.get(STEP_UP).json()["seconds_left"] == 0
    assert SecurityEvent.objects.filter(kind=SecurityEventKind.STEP_UP_FAILED).exists()


def test_the_limiter_covers_the_step_up_prompt_when_it_is_on():
    """It is a password prompt like the sign-in form, so it gets the same
    treatment — otherwise it would be the softer way in."""
    client = staff_client()
    arm(step_up=True, login_rate_limit=True, login_max_attempts=2, login_lockout_seconds=900)

    assert confirm(client, "wrong").status_code == 401
    assert confirm(client, "wrong").status_code == 401

    locked = confirm(client)
    assert locked.status_code == 429
    assert locked.json()["code"] == "rate_limited"
