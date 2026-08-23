"""A credential that stops working without the exchange ever saying so.

Hyperliquid prunes an agent wallet at its expiry: no refusal, no error code, the
account just stops trading. ``apps.accounts.credentials`` turns that silence
into a countdown, and these tests pin the parts that make the countdown worth
trusting — that it warns before the date rather than after it, that it does not
pile up a notice per poll, and that renewing the key clears what is standing
without anyone dismissing it by hand.

They also pin what it deliberately does *not* do: nothing here pauses an
account or removes it from a fan-out. An expiring credential is a working
credential.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings
from django.utils import timezone

from apps.accounts import credentials
from apps.accounts.models import (
    AccountStatus,
    ConnectedAccount,
    Exchange,
    Notification,
)

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db


def make_account(label: str = "partner-hl", **overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=overrides.pop("exchange", Exchange.HYPERLIQUID),
        status=overrides.pop("status", AccountStatus.ACTIVE),
        withdrawal_check_passed=True,
        withdrawal_checked_at=timezone.now(),
        last_balance=overrides.pop("last_balance", "1000"),
        last_balance_asset=overrides.pop("last_balance_asset", "USDT"),
        **overrides,
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


def in_days(n: float):
    return timezone.now() + timedelta(days=n)


# --- the countdown ---------------------------------------------------------


def test_an_account_with_no_recorded_expiry_is_never_warned_about():
    """Most exchanges have no expiry at all, and a blank is not a warning.

    Guessing 180 days from connect time would put a confident wrong date on
    screen for seven of the eight venues.
    """
    account = make_account(exchange=Exchange.BYBIT)
    assert account.credential_days_left is None
    assert account.credential_state == credentials.OK


def test_days_left_rounds_down_so_one_day_never_means_twenty_minutes():
    account = make_account(credential_expires_at=in_days(5.9))
    assert account.credential_days_left == 5


def test_an_expired_credential_reports_how_long_it_has_been_dead():
    """Negative, not clamped at zero: the number dates the outage."""
    account = make_account(credential_expires_at=in_days(-3.5))
    assert account.credential_days_left == -4
    assert account.credential_state == credentials.EXPIRED


@override_settings(CREDENTIALS={"EXPIRY_WARN_DAYS": 21, "MAX_AGENT_DAYS": 180})
def test_the_warning_window_opens_before_the_date_not_on_it():
    outside = make_account("far", credential_expires_at=in_days(40))
    inside = make_account("near", credential_expires_at=in_days(20))
    assert outside.credential_state == credentials.OK
    assert inside.credential_state == credentials.EXPIRING


# --- the notice ------------------------------------------------------------


def test_one_notice_per_account_no_matter_how_often_the_panel_polls():
    """The panel polls balances every 45s. A notice per poll is not a warning."""
    make_account(credential_expires_at=in_days(3))
    for _ in range(5):
        credentials.sync_notifications()
    assert Notification.objects.filter(dismissed_at__isnull=True).count() == 1


def test_crossing_into_expired_replaces_the_notice_rather_than_adding_one():
    account = make_account(credential_expires_at=in_days(2))
    credentials.sync_notifications()
    account.credential_expires_at = in_days(-1)
    account.save(update_fields=["credential_expires_at"])
    credentials.sync_notifications()

    active = Notification.objects.filter(dismissed_at__isnull=True)
    assert [n.code for n in active] == ["credential_expired"]


def test_renewing_the_key_clears_the_notice_without_anyone_dismissing_it():
    """The admin can end this condition, unlike a failed order.

    Spec §4's rule that a notice never expires on its own is about a failure
    that already happened. This one is a countdown, and a countdown that has
    been reset is a stale claim by the platform, not news.
    """
    account = make_account(credential_expires_at=in_days(2))
    credentials.sync_notifications()
    assert Notification.objects.filter(dismissed_at__isnull=True).count() == 1

    account.credential_expires_at = in_days(179)
    account.save(update_fields=["credential_expires_at"])
    credentials.sync_notifications()
    assert not Notification.objects.filter(dismissed_at__isnull=True).exists()


def test_a_paused_account_is_not_warned_about():
    """It is not trading either way; the notice would be noise until resumed."""
    make_account(status=AccountStatus.PAUSED, credential_expires_at=in_days(1))
    credentials.sync_notifications()
    assert not Notification.objects.filter(dismissed_at__isnull=True).exists()


# --- what it must not do ---------------------------------------------------


def test_an_expiring_credential_still_trades():
    """Reported, never enforced.

    An account removed from the fan-out because a date is near is an account
    that stopped trading early for a reason the exchange never gave.
    """
    account = make_account(credential_expires_at=in_days(1))
    assert account.is_tradeable

    account.credential_expires_at = in_days(-1)
    account.save(update_fields=["credential_expires_at"])
    assert account.is_tradeable


def test_expiring_reports_the_soonest_first_and_ignores_healthy_accounts():
    make_account("soon", credential_expires_at=in_days(2))
    make_account("sooner", credential_expires_at=in_days(-1))
    make_account("fine", credential_expires_at=in_days(120))
    make_account("no-expiry", exchange=Exchange.BYBIT)

    rows = credentials.expiring(ConnectedAccount.objects.all())
    assert [r.label for r in rows] == ["sooner", "soon"]


def test_the_ceiling_is_the_exchange_maximum_not_an_invented_default():
    """180 days is used to reject a typo, never to fill in a missing date."""
    now = timezone.now()
    assert credentials.ceiling(now) == now + timedelta(days=180)
    assert make_account(exchange=Exchange.BYBIT).credential_expires_at is None
