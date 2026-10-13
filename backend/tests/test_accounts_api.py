"""Spec §6 account lifecycle and the spec §7 checks attached to it.

The §7 rule is narrow and worth restating, because two of these tests exist to
keep it that way: a key *proven* withdrawable is refused; a key whose
permissions the exchange will not publish is flagged, not refused. Five of the
eight exchanges publish nothing, so the stricter reading would ban them.
"""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts import views as account_views
from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D
from apps.exchanges.base import WithdrawalPermissionError

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db


def staff_client() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


def make_account(**overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=overrides.pop("label", "partner-a"),
        exchange=overrides.pop("exchange", Exchange.BYBIT),
        status=overrides.pop("status", AccountStatus.PAUSED),
        withdrawal_check_passed=overrides.pop("withdrawal_check_passed", True),
        withdrawal_checked_at=overrides.pop("withdrawal_checked_at", timezone.now()),
        **overrides,
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_resume_re_runs_the_withdrawal_check(monkeypatch):
    """G5: permissions can change while an account sits paused.

    Resume used to flip the status and nothing else, so a key that had gained
    withdrawal rights meanwhile went straight back to routing partner capital.
    """
    calls: list[int] = []

    def fake_verify(account):
        calls.append(account.id)
        return True, ""

    monkeypatch.setattr(account_views, "verify_account", fake_verify)
    account = make_account(withdrawal_checked_at=None, withdrawal_check_passed=False)

    response = staff_client().post(f"/api/accounts/accounts/{account.id}/resume/")

    assert response.status_code == 200
    assert calls == [account.id], "resume did not re-verify the credential"
    account.refresh_from_db()
    assert account.status == AccountStatus.ACTIVE
    assert account.withdrawal_checked_at is not None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_resume_refuses_a_key_that_has_gained_withdrawal_rights(monkeypatch):
    """Spec §7 is a hard refusal wherever the exchange will tell us."""

    def fake_verify(account):
        raise WithdrawalPermissionError("bybit: this API key has withdrawal permission.")

    monkeypatch.setattr(account_views, "verify_account", fake_verify)
    account = make_account()

    response = staff_client().post(f"/api/accounts/accounts/{account.id}/resume/")

    assert response.status_code == 400
    account.refresh_from_db()
    assert account.status == AccountStatus.PAUSED, "a withdrawable key was activated"
    assert account.withdrawal_check_passed is False
    assert "withdrawal" in account.last_error


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_unprovable_check_still_resumes_but_stays_flagged(monkeypatch):
    """KuCoin, Gate.io, Toobit, LBank and Hyperliquid publish no permission
    endpoint. They connect flagged — refusing them would be a rule §7 does not
    state, and would leave five exchanges unusable."""

    def fake_verify(account):
        return False, "kucoin: no key-permission endpoint on the futures host"

    monkeypatch.setattr(account_views, "verify_account", fake_verify)
    account = make_account(exchange=Exchange.KUCOIN, withdrawal_check_passed=False)

    response = staff_client().post(f"/api/accounts/accounts/{account.id}/resume/")

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.status == AccountStatus.ACTIVE
    assert account.withdrawal_check_passed is False
    assert account.last_error


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_paper_account_resumes_without_touching_an_exchange(monkeypatch):
    """Spec §9's demo mode holds no credentials to check."""

    def explode(account):  # pragma: no cover - must never be called
        raise AssertionError("the paper adapter has no exchange to ask")

    monkeypatch.setattr(account_views, "verify_account", explode)
    account = ConnectedAccount.objects.create(
        label="demo",
        exchange=Exchange.PAPER,
        status=AccountStatus.PAUSED,
        withdrawal_check_passed=True,
    )

    response = staff_client().post(f"/api/accounts/accounts/{account.id}/resume/")

    assert response.status_code == 200


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_clean_refuses_to_activate_an_unchecked_account():
    """The §7 guard is live, not dormant: it gates on *checked*, not *passed*."""
    account = make_account(status=AccountStatus.ACTIVE, withdrawal_checked_at=None)

    with pytest.raises(ValidationError) as caught:
        account.full_clean()
    assert "withdrawal_checked_at" in caught.value.error_dict

    account.withdrawal_checked_at = timezone.now()
    account.full_clean()  # must not raise

    # A checked-but-unprovable account is allowed through: that is the whole
    # point of storing the timestamp separately from the verdict.
    account.withdrawal_check_passed = False
    account.full_clean()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_pause_leaves_the_account_untouched_apart_from_its_status():
    """Spec §6: pause is not a disconnect — the position is left as-is, and
    ``services.eligible_accounts`` still closes it (see test_services)."""
    account = make_account(status=AccountStatus.ACTIVE)

    response = staff_client().post(f"/api/accounts/accounts/{account.id}/pause/")

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.status == AccountStatus.PAUSED
    assert account.withdrawal_checked_at is not None


# --- who drives the account (Q42) -------------------------------------------
#
# One hand per account: the admin's ticket (``bot`` null) or one bot. See
# ``apps.trading.services.eligible_accounts`` for the filtering itself.


def _assign(client, account, bot, **extra):
    return client.post(
        f"/api/accounts/accounts/{account.id}/assign/",
        data={"bot": bot.id if bot else None, **extra},
        content_type="application/json",
    )


def _open_leg(account, symbol="BTCUSDT"):
    from apps.trading.models import Trade, TradeLeg

    trade = Trade.objects.create(
        symbol=symbol, side="long", market="futures", order_type="market", leverage=5
    )
    TradeLeg.objects.create(trade=trade, account=account, ok=True, qty=D("1"))
    return trade


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_account_is_manual_until_a_bot_is_assigned():
    """A bot fanning out to an account nobody handed it is the mistake the
    default guards against."""
    assert make_account().bot_id is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_account_can_be_handed_to_a_bot_and_back():
    from tests.bot_factory import make_bot

    account = make_account()
    bot = make_bot(name="trend")
    client = staff_client()

    response = _assign(client, account, bot)
    assert response.status_code == 200
    assert response.json()["bot"] == bot.id
    assert response.json()["bot_name"] == "trend"

    response = _assign(client, account, None)
    assert response.status_code == 200
    account.refresh_from_db()
    assert account.bot_id is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_handing_an_account_over_records_who_did_it(caplog):
    """Two people share the panel's login screen, not the login.

    Which hand took the account is already in the log; on a book somebody
    else's money is in, *who* moved it is the half nobody can reconstruct
    afterwards — and it is what the Telegram notice carries.
    """
    from tests.bot_factory import make_bot

    account = make_account()
    bot = make_bot(name="trend")
    with caplog.at_level(logging.INFO, logger="apps.accounts.views"):
        _assign(staff_client(), account, bot)

    [record] = [r for r in caplog.records if getattr(r, "error_code", "") == "account_changed"]
    assert record.context["actor"] == "boss"
    assert record.context["changed"] == "driven by trend"
    assert "boss" in record.getMessage()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_account_holding_a_position_is_not_handed_over_silently():
    from tests.bot_factory import make_bot

    account = make_account()
    trade = _open_leg(account)

    response = _assign(staff_client(), account, make_bot())

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "account_has_position"
    assert body["trade_id"] == trade.id
    assert body["symbol"] == "BTCUSDT"
    account.refresh_from_db()
    assert account.bot_id is None


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_confirming_closes_that_accounts_leg_only_and_then_hands_it_over(monkeypatch):
    from apps.engine.fanout import FanOutResult, LegResult
    from apps.trading import services
    from tests.bot_factory import make_bot

    account = make_account()
    trade = _open_leg(account)
    bot = make_bot()
    calls = []

    async def fake_close(*, trade, account_ids=None):
        calls.append((trade.id, account_ids))
        return FanOutResult(
            legs=[LegResult(account_id=account.id, ok=True, value=None, duration_ms=1.0)],
            total_ms=1.0,
        )

    monkeypatch.setattr(services, "route_close", fake_close)

    response = _assign(staff_client(), account, bot, close_position=True)

    assert response.status_code == 200
    assert calls == [(trade.id, [account.id])]
    account.refresh_from_db()
    assert account.bot_id == bot.id


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_close_the_exchange_did_not_confirm_keeps_the_assignment(monkeypatch):
    from apps.engine.fanout import FanOutResult, LegResult
    from apps.trading import services
    from tests.bot_factory import make_bot

    account = make_account()
    _open_leg(account)

    async def failing_close(*, trade, account_ids=None):
        return FanOutResult(
            legs=[
                LegResult(
                    account_id=account.id,
                    ok=False,
                    error="venue down",
                    error_code="exchange_error",
                    duration_ms=1.0,
                )
            ],
            total_ms=1.0,
        )

    monkeypatch.setattr(services, "route_close", failing_close)

    response = _assign(staff_client(), account, make_bot(), close_position=True)

    assert response.status_code == 502
    assert response.json()["code"] == "close_failed"
    account.refresh_from_db()
    assert account.bot_id is None
