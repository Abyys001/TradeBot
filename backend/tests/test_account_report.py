"""The per-account report: one connection's whole record in one payload.

Two things are worth pinning. The arithmetic — an account's realised PnL, win
rate and cash flows have to agree with the ledger and the trade legs they are
derived from, because this page is where a partner's number gets read. And the
access rule — a report is a detail route on the accounts viewset, so an account
the caller cannot list must not be readable by guessing its id.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import (
    AccountStatus,
    ConnectedAccount,
    Exchange,
    FundMovement,
    FundMovementType,
)
from apps.accounts.report import account_report
from apps.trading.models import Trade, TradeLeg

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db


def make_account(label="partner-a", **overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=overrides.pop("exchange", Exchange.BYBIT),
        status=overrides.pop("status", AccountStatus.ACTIVE),
        withdrawal_check_passed=True,
        withdrawal_checked_at=timezone.now(),
        last_balance=overrides.pop("last_balance", Decimal("1200")),
        last_balance_asset=overrides.pop("last_balance_asset", "USDT"),
        **overrides,
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


def add_leg(account, *, symbol="BTCUSDT", pnl=None, ok=True, closed=True, margin="100"):
    trade = Trade.objects.create(symbol=symbol, side="long", leverage=10)
    return TradeLeg.objects.create(
        trade=trade,
        account=account,
        ok=ok,
        qty=Decimal("0.01"),
        entry_price=Decimal("50000"),
        margin=Decimal(margin),
        pnl=None if pnl is None else Decimal(pnl),
        closed_at=timezone.now() if closed else None,
    )


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_summary_counts_only_priced_legs():
    """An unpriced leg is unknown, not a break-even trade.

    Counting it would drag the win rate toward 50% and the average toward zero
    with a number no exchange ever returned.
    """
    account = make_account()
    add_leg(account, pnl="30")
    add_leg(account, pnl="-10", symbol="ETHUSDT")
    add_leg(account, pnl=None)
    add_leg(account, ok=False, pnl=None)

    report = account_report(account)
    summary = report["trading"]

    assert summary["legs"] == 4
    assert summary["failed"] == 1
    assert summary["scored"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert Decimal(summary["realised_pnl"]) == Decimal("20")
    assert Decimal(summary["win_rate"]) == Decimal("50")
    assert Decimal(summary["best"]) == Decimal("30")
    assert Decimal(summary["worst"]) == Decimal("-10")
    assert Decimal(summary["profit_factor"]) == Decimal("3")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_curve_accumulates_oldest_first():
    account = make_account()
    add_leg(account, pnl="10")
    add_leg(account, pnl="-4")
    add_leg(account, pnl="7")

    curve = account_report(account)["curve"]

    assert [Decimal(point["cumulative"]) for point in curve] == [
        Decimal("10"),
        Decimal("6"),
        Decimal("13"),
    ]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_money_matches_the_ledger():
    """The report must not be a second opinion about one account's PnL."""
    account = make_account(last_balance=Decimal("1200"))
    FundMovement.objects.create(
        account=account, kind=FundMovementType.DEPOSIT, amount=Decimal("1000")
    )
    FundMovement.objects.create(
        account=account, kind=FundMovementType.WITHDRAWAL, amount=Decimal("100")
    )

    report = account_report(account)

    assert Decimal(report["ledger"]["net_invested"]) == Decimal("900")
    assert Decimal(report["ledger"]["pnl"]) == Decimal("300")
    assert len(report["movements"]) == 2


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_report_is_staff_only_and_respects_visibility():
    """A hidden account is a 404 here, exactly as it is in the list."""
    hidden = make_account(label="quiet", hidden=True)
    visible = make_account(label="loud")

    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")

    assert client.get(f"/api/accounts/accounts/{visible.id}/report/").status_code == 200
    assert client.get(f"/api/accounts/accounts/{hidden.id}/report/").status_code == 404

    anonymous = Client()
    assert anonymous.get(f"/api/accounts/accounts/{visible.id}/report/").status_code in (401, 403)
