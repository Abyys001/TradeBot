"""The warm-adapter pool (apps.exchanges.pool).

What these pin is the reason the pool exists and the reason it is safe:

  - an account reuses *its own* adapter across actions, so a leg no longer pays
    a TCP+TLS handshake (and, on Hyperliquid, a metadata download) inside the
    spec §4 deadline;
  - two accounts never share one, which is the structural half of the spec §2
    isolation guarantee;
  - a re-keyed account gets a new adapter rather than one signing with
    credentials the admin has replaced.
"""

from __future__ import annotations

import asyncio

import pytest
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D
from apps.exchanges import pool
from apps.exchanges.rest import default_timeout

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

KEY = Fernet.generate_key().decode()


@sync_to_async
def make_account(label: str, **kwargs) -> ConnectedAccount:
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D("1000"),
        last_balance_asset="USDT",
        **kwargs,
    )


@sync_to_async
def rekey(account: ConnectedAccount, secret: str) -> ConnectedAccount:
    account.set_credentials(api_key="key", api_secret=secret)
    account.save()
    return ConnectedAccount.objects.get(pk=account.pk)


@sync_to_async
def reload(account: ConnectedAccount) -> ConnectedAccount:
    return ConnectedAccount.objects.get(pk=account.pk)


@pytest.fixture(autouse=True)
async def _clean_pool():
    await pool.aclose_all()
    yield
    await pool.aclose_all()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_same_account_reuses_one_adapter():
    """The whole point: the second action does not open a new connection."""
    account = await make_account("Master")

    first = pool.get(account)
    second = pool.get(await reload(account))

    assert first is second


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_two_accounts_never_share_an_adapter():
    """Spec §2: one account's client, limiter and credentials are its own."""
    one = await make_account("Master")
    two = await make_account("Partner")

    assert pool.get(one) is not pool.get(two)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_re_keying_an_account_retires_its_adapter():
    """A warm adapter must never outlive the credentials it signs with."""
    account = await make_account("Master")
    account = await rekey(account, "first-secret")
    first = pool.get(account)

    second = pool.get(await rekey(account, "second-secret"))

    assert second is not first


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_deleting_an_account_retires_its_adapter():
    """post_delete is the one invalidation a re-read of the row cannot do."""
    account = await make_account("Master")
    pool.get(account)
    account_id = account.id

    await sync_to_async(account.delete)()

    assert account_id not in pool._pool


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_hyperliquid_adapter_builds_its_sdk_once():
    """A leg opens with three concurrent calls, on one cold adapter.

    Without the build lock each of them saw ``_exchange is None`` and built the
    SDK — which downloads the asset metadata. Three metadata downloads, inside
    the per-leg deadline, on the first order after a restart.
    """
    from apps.exchanges.hyperliquid import HyperliquidAdapter

    adapter = HyperliquidAdapter(
        agent_private_key="0x" + "11" * 32,
        account_address="0x" + "22" * 20,
    )
    builds = 0

    def fake_build() -> None:
        nonlocal builds
        builds += 1
        adapter._exchange = object()
        adapter._info = object()

    adapter._build = fake_build
    await asyncio.gather(*(adapter._ensure_built() for _ in range(3)))

    assert builds == 1


@pytest.mark.parametrize(("budget", "expected"), [(3.0, 2.25), (8.0, 6.0), (0.4, 0.8)])
async def test_the_request_timeout_follows_the_deadline(settings, budget, expected):
    """Raising the per-leg deadline has to buy a request more patience.

    It did not before: the request ceiling was a hardcoded 0.8s, so a healthy
    but distant venue timed out however generous the deadline was — which is
    what made a VPS order fail as ``exceeded the deadline`` on a leg that was
    still perfectly on track. The last case is the floor: an absurdly small
    deadline must not produce a timeout no request could ever meet.
    """
    settings.TRADING = {**settings.TRADING, "FANOUT_TIMEOUT_SECONDS": budget}

    assert default_timeout() == pytest.approx(expected)
