"""Spec §6 account lifecycle and the spec §7 checks attached to it.

The §7 rule is narrow and worth restating, because two of these tests exist to
keep it that way: a key *proven* withdrawable is refused; a key whose
permissions the exchange will not publish is flagged, not refused. Five of the
eight exchanges publish nothing, so the stricter reading would ban them.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts import views as account_views
from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
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


# --- manual/bot trading switches --------------------------------------------
#
# Two independent on/off controls on whether a *new* entry may reach this
# account: the admin's own ticket, and a running bot's. See
# ``apps.trading.services.eligible_accounts`` for the filtering itself.


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_manual_trading_defaults_on_and_bot_trading_defaults_off():
    """Every account already trades manually today; a bot fanning out to an
    account nobody opted in is the mistake the default guards against."""
    account = make_account()
    assert account.manual_trading_enabled is True
    assert account.bot_trading_enabled is False


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_manual_trading_can_be_switched_off():
    account = make_account()

    response = staff_client().post(
        f"/api/accounts/accounts/{account.id}/manual-trading/", data={"enabled": False},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["manual_trading_enabled"] is False
    account.refresh_from_db()
    assert account.manual_trading_enabled is False
    # The other switch, and everything else about the account, is untouched.
    assert account.bot_trading_enabled is False
    assert account.status == AccountStatus.PAUSED


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_bot_trading_can_be_switched_on():
    account = make_account()

    response = staff_client().post(
        f"/api/accounts/accounts/{account.id}/bot-trading/", data={"enabled": True},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["bot_trading_enabled"] is True
    account.refresh_from_db()
    assert account.bot_trading_enabled is True
    # The other switch is untouched.
    assert account.manual_trading_enabled is True
