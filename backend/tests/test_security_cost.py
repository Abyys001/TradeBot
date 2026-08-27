"""`docs/security-plan.md` §1 — what the security layer costs the money path.

The first constraint on this layer was that it must not slow the platform down,
and the second was that with everything off the code that runs is the code that
ran before it existed. Both are measurable, so both are measured here rather
than asserted in a comment.

Three separate claims, because they have three different proofs:

* **Off costs nothing.** With every switch off the request middleware performs
  a dictionary lookup and returns; the query count of a request is the same as
  it is with the middleware removed from the stack entirely.
* **On costs nothing *on the routing path*.** Step-up and the write limiter are
  wired to skip `orders/`, `balances/`, `stop-all/` and `bots/` whatever their
  switch says, and the allowlist exempts the halt. So an order routes the same
  with every control armed as with none.
* **On costs one session write per request, everywhere else.** That is
  `idle_timeout`, which asks Django to move the session's deadline forward. It
  is the only per-request write this layer can add, and naming its price here
  is what stops it growing a second one unnoticed.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D
from apps.security import flags
from apps.security.models import CspMode, SecurityPolicy

KEY = Fernet.generate_key().decode()

POLICY = "/api/trading/policy/"
STOP_ALL = "/api/trading/stop-all/"
OPEN = "/api/trading/orders/open/"
SECURITY_POLICY = "/api/security/policy/"

#: Every switch armed, plus the tunables set so the limiters would fire on the
#: very next request. A control that is on but too generous to trigger proves
#: nothing about whether it is on the routing path.
ARMED = {
    "two_factor": True,
    "trusted_devices": True,
    "login_rate_limit": True,
    "new_device_notice": True,
    "idle_timeout": True,
    "single_session": True,
    "ip_allowlist": True,
    "step_up": True,
    "audit_log": True,
    "admin_write_rate_limit": True,
    "csp_mode": CspMode.ENFORCE,
    "admin_write_max_per_minute": 1,
    "allowed_ips": "127.0.0.1",
}


def arm(**overrides) -> None:
    """Write the policy row straight through, past `set_flags`' guards.

    `set_flags` refuses to arm two-factor with nobody enrolled, which is the
    right refusal for an operator and the wrong one here: the point of this
    file is the *most* hostile configuration the switches allow.
    """
    SecurityPolicy.objects.update_or_create(pk=1, defaults={**ARMED, **overrides})
    flags.invalidate()
    flags.policy()


def staff_client() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


def account(label: str, *, balance: str = "1000") -> ConnectedAccount:
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D(balance),
        last_balance_asset="USDT",
    )


def order(**overrides) -> dict:
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


# --------------------------------------------------------------------------
# Off costs nothing
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_warm_snapshot_costs_no_query_and_no_cache_read(monkeypatch):
    """The whole design in one assertion: `peek` is memory, not I/O."""
    flags.policy()  # warm the process-local memo

    monkeypatch.setattr(cache, "get", lambda *a, **k: pytest.fail("peek read the cache"))
    values = flags.peek()

    assert values is not None
    assert values["_middleware_active"] is False


@pytest.mark.django_db
def test_peek_returns_nothing_once_the_memo_has_expired():
    """The other half of it — an expired memo must not serve a stale answer."""
    flags.policy()
    flags.invalidate()

    assert flags.peek() is None


def queries_for(call) -> int:
    """Queries for one request, after a warm-up request.

    The first request of a test pays for things that are not this layer and do
    not repeat — the kill-switch cache, the session row's first `last_seen`
    write, DRF's own lazy imports. Measuring the second one is what makes the
    number comparable at all.
    """
    call()
    with CaptureQueriesContext(connection) as captured:
        response = call()
    assert response.status_code == 200, response.content
    return len(captured)


@pytest.mark.django_db
def test_with_everything_off_the_middleware_is_not_in_the_way():
    """Same request, same query count, with and without this layer installed."""
    from django.conf import settings

    client = staff_client()
    flags.policy()

    without = [m for m in settings.MIDDLEWARE if "apps.security" not in m]
    assert len(without) == len(settings.MIDDLEWARE) - 1

    with override_settings(MIDDLEWARE=without):
        baseline = queries_for(lambda: client.get(POLICY))

    assert queries_for(lambda: client.get(POLICY)) == baseline


# --------------------------------------------------------------------------
# On costs nothing on the routing path
# --------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_order_routes_with_every_control_armed():
    """Step-up is on with no grant, the write limiter is at one per minute,
    the allowlist is on — and the order still goes out, because none of the
    three is allowed to look at `orders/`."""
    account("one")
    client = staff_client()
    arm()

    for _ in range(3):
        response = client.post(OPEN, order(), content_type="application/json")
        assert response.status_code in (200, 409), response.content
        assert response.status_code != 429
        assert response.status_code != 403


@pytest.mark.django_db
def test_the_halt_answers_from_an_address_the_allowlist_does_not_know():
    """A lock-out that also disables the brake is the failure this layer is
    designed around, so `stop-all` is exempt from the allowlist by name."""
    client = staff_client()
    arm(allowed_ips="10.9.9.9")

    assert client.get(POLICY).status_code == 403
    assert client.get(STOP_ALL).status_code == 200
    halted = client.post(STOP_ALL, {"on": True}, content_type="application/json")
    assert halted.status_code == 200, halted.content


@pytest.mark.django_db
def test_the_write_limiter_stops_an_admin_write_but_not_a_routed_one():
    """The limiter has to be doing something, or the test above proves nothing."""
    client = staff_client()
    arm()

    first = client.post(SECURITY_POLICY, {"audit_log": True}, content_type="application/json")
    second = client.post(SECURITY_POLICY, {"audit_log": True}, content_type="application/json")

    assert 429 in (first.status_code, second.status_code)


# --------------------------------------------------------------------------
# On costs one session write, and only that
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_arming_everything_but_the_idle_timeout_adds_no_query():
    client = staff_client()
    flags.policy()
    baseline = queries_for(lambda: client.get(POLICY))

    arm(idle_timeout=False)

    assert queries_for(lambda: client.get(POLICY)) == baseline


@pytest.mark.django_db
def test_the_idle_timeout_costs_exactly_one_session_write():
    client = staff_client()
    flags.policy()
    baseline = queries_for(lambda: client.get(POLICY))

    arm(ip_allowlist=False, admin_write_rate_limit=False)
    client.get(POLICY)
    with CaptureQueriesContext(connection) as captured:
        assert client.get(POLICY).status_code == 200

    statements = [
        query["sql"]
        for query in captured.captured_queries
        if not query["sql"].startswith(("SAVEPOINT", "RELEASE SAVEPOINT"))
    ]
    writes = [sql for sql in statements if sql.startswith(("UPDATE", "INSERT"))]

    assert len(statements) == baseline + 1
    assert len(writes) == 1
    assert 'UPDATE "django_session"' in writes[0]
