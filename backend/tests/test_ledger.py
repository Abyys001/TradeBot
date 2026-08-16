"""The financial ledger: math, the split, and the movement API.

The ledger combines two sources that must never be confused: ``FundMovement``
rows (entered by hand — keys are trade-only, spec §7) and
``ConnectedAccount.last_balance`` (the exchange's live number). The tests pin
the arithmetic in Decimal, the profit-only rule (a loss divides into nothing),
and the "unknown, not zero" rule for unpriced accounts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.ledger import account_ledger, aggregate, ledger_snapshot
from apps.accounts.models import (
    AccountStatus,
    ConnectedAccount,
    Exchange,
    FundMovement,
    FundMovementType,
)
from apps.core.money import D

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db


def staff_client() -> Client:
    user, _ = User.objects.get_or_create(username="boss", defaults={"is_staff": True})
    user.set_password("pw12345!")
    user.is_staff = True
    user.save()
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


def make_account(label: str = "partner-a", **overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=overrides.pop("exchange", Exchange.PAPER),
        status=overrides.pop("status", AccountStatus.ACTIVE),
        withdrawal_check_passed=True,
        withdrawal_checked_at=timezone.now(),
        last_balance=overrides.pop("last_balance", "100"),
        last_balance_asset=overrides.pop("last_balance_asset", "USDT"),
        **overrides,
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


def movement(account: ConnectedAccount, kind: str, amount: str, **overrides) -> FundMovement:
    return FundMovement.objects.create(
        account=account,
        kind=kind,
        amount=amount,
        **overrides,
    )


# --- the arithmetic ----------------------------------------------------------


def test_deposits_minus_withdrawals_is_net_invested():
    account = make_account(last_balance="110.5")
    movement(account, FundMovementType.DEPOSIT, "100")
    movement(account, FundMovementType.WITHDRAWAL, "5")

    row = account_ledger(account)

    assert D(row["deposits"]) == Decimal("100")
    assert D(row["withdrawals"]) == Decimal("5")
    assert D(row["net_invested"]) == Decimal("95")
    assert D(row["current_balance"]) == Decimal("110.5")
    assert D(row["pnl"]) == Decimal("15.5")


def test_pnl_percentage_and_shares():
    account = make_account(last_balance="110.5")
    movement(account, FundMovementType.DEPOSIT, "100")
    movement(account, FundMovementType.WITHDRAWAL, "5")

    row = account_ledger(account)

    assert D(row["pnl_pct"]) == Decimal("16.31578947368421052631578947")
    # 15.5 profit split 60/20/20 -> 9.3 / 3.1 / 3.1.
    assert {role: D(v) for role, v in row["shares"].items()} == {
        "investor": Decimal("9.3"),
        "trader": Decimal("3.1"),
        "programmer": Decimal("3.1"),
    }


def test_a_loss_splits_into_nothing():
    """Profit-only rule: when there is a loss there is nothing to divide."""
    account = make_account(last_balance="90")
    movement(account, FundMovementType.DEPOSIT, "100")

    row = account_ledger(account)

    assert D(row["pnl"]) == Decimal("-10")
    assert {role: D(v) for role, v in row["shares"].items()} == {
        "investor": Decimal("0"),
        "trader": Decimal("0"),
        "programmer": Decimal("0"),
    }


def test_an_unpriced_account_is_unknown_not_zero():
    account = make_account(last_balance=None, last_balance_asset="")

    row = account_ledger(account)

    assert row["current_balance"] is None
    assert row["pnl"] is None
    assert row["pnl_pct"] is None


def test_no_balance_no_net_means_no_percentage():
    account = make_account(last_balance="50")

    row = account_ledger(account)

    assert D(row["net_invested"]) == Decimal("0")
    assert row["pnl_pct"] is None, "dividing by zero must not happen"


def test_a_no_movement_account_reports_balance_as_pnl_but_no_percentage():
    account = make_account(last_balance="50")
    row = account_ledger(account)
    assert D(row["net_invested"]) == Decimal("0")
    assert D(row["pnl"]) == Decimal("50")
    # Zero invested capital has no denominator: no percentage, not a fake 100%.
    assert row["pnl_pct"] is None


# --- aggregation -------------------------------------------------------------


def test_aggregate_sums_groups_and_recomputes_percentage():
    rows = [
        account_ledger(make_account("a", last_balance="110")),
        account_ledger(make_account("b", last_balance="55")),
    ]
    a = ConnectedAccount.objects.get(id=rows[0]["account"])
    b = ConnectedAccount.objects.get(id=rows[1]["account"])
    movement(a, FundMovementType.DEPOSIT, "100")
    movement(b, FundMovementType.DEPOSIT, "50")

    group = aggregate([account_ledger(a), account_ledger(b)])

    assert group["accounts"] == 2
    assert D(group["net_invested"]) == Decimal("150")
    assert D(group["current_balance"]) == Decimal("165")
    assert D(group["pnl"]) == Decimal("15")
    assert D(group["pnl_pct"]) == Decimal("10")


def test_unpriced_and_non_usdt_rows_stay_out_of_the_totals():
    priced = make_account("priced", last_balance="110")
    movement(priced, FundMovementType.DEPOSIT, "100")
    unpriced = make_account("unpriced", last_balance=None, last_balance_asset="")
    btc = make_account("btc", last_balance_asset="BTC", last_balance="0.1")
    movement(btc, FundMovementType.DEPOSIT, "1")

    group = aggregate(
        [account_ledger(priced), account_ledger(unpriced), account_ledger(btc)]
    )

    assert group["accounts"] == 1, "only the priced USDT row may join the totals"
    assert D(group["net_invested"]) == Decimal("100")
    assert D(group["current_balance"]) == Decimal("110")


def test_snapshot_groups_by_exchange_and_flags_non_usdt():
    bybit_a = make_account("a", exchange=Exchange.BYBIT, last_balance="110")
    movement(bybit_a, FundMovementType.DEPOSIT, "100")
    bybit_b = make_account("b", exchange=Exchange.BYBIT, last_balance="22")
    movement(bybit_b, FundMovementType.DEPOSIT, "20")
    btc = make_account("btc", exchange=Exchange.PAPER, last_balance_asset="BTC", last_balance="0.1")

    snapshot = ledger_snapshot(ConnectedAccount.objects.all())

    assert [g["exchange"] for g in snapshot["exchanges"]] == ["bybit", "paper"]
    bybit = snapshot["exchanges"][0]
    assert bybit["accounts"] == 2
    assert bybit["current_balance"] == "132.00000000"
    assert bybit["pnl"] == "12.00000000"
    assert snapshot["non_usdt"] == [
        {"account": btc.id, "label": "btc", "asset": "BTC"}
    ]
    # The non-USDT exchange group aggregates nothing: its only row is flagged.
    paper = snapshot["exchanges"][1]
    assert paper["accounts"] == 0


# --- the split config --------------------------------------------------------


def test_split_defaults_to_the_seeded_percentages():
    snapshot = ledger_snapshot(ConnectedAccount.objects.none())
    assert {role: D(v) for role, v in snapshot["split"].items()} == {
        "investor": Decimal("60"),
        "trader": Decimal("20"),
        "programmer": Decimal("20"),
    }


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_split_endpoint_rejects_a_sum_that_is_not_100():
    response = staff_client().post(
        "/api/accounts/ledger/split/",
        {"investor": 70, "trader": 20, "programmer": 20},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "investor" in response.json()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_split_endpoint_rejects_values_out_of_range():
    response = staff_client().post(
        "/api/accounts/ledger/split/",
        {"investor": -10, "trader": 60, "programmer": 50},
        content_type="application/json",
    )
    assert response.status_code == 400

    response = staff_client().post(
        "/api/accounts/ledger/split/",
        {"investor": 120, "trader": -10, "programmer": -10},
        content_type="application/json",
    )
    assert response.status_code == 400


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_split_endpoint_updates_and_records_who_did_it():
    response = staff_client().post(
        "/api/accounts/ledger/split/",
        {"investor": 50, "trader": 30, "programmer": 20},
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["investor"] == "50.00"
    assert body["trader"] == "30.00"
    assert body["programmer"] == "20.00"
    assert body["updated_by"] == "boss"

    shown = staff_client().get("/api/accounts/ledger/split/").json()
    assert shown["investor"] == "50.00"
    assert shown["trader"] == "30.00"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_shares_recompute_after_the_split_changes():
    account = make_account(last_balance="110")
    movement(account, FundMovementType.DEPOSIT, "100")

    staff_client().post(
        "/api/accounts/ledger/split/",
        {"investor": 40, "trader": 35, "programmer": 25},
        content_type="application/json",
    )

    row = account_ledger(account)
    assert {role: D(v) for role, v in row["shares"].items()} == {
        "investor": Decimal("4"),
        "trader": Decimal("3.5"),
        "programmer": Decimal("2.5"),
    }


# --- the movement API --------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_create_a_movement():
    account = make_account()
    response = staff_client().post(
        "/api/accounts/ledger/movements/",
        {"account": account.id, "kind": "deposit", "amount": "100.5", "note": "alice"},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["amount"] == "100.50000000"
    assert body["account_label"] == "partner-a"
    assert FundMovement.objects.filter(account=account, kind="deposit").count() == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_movement_amount_must_be_positive():
    account = make_account()
    response = staff_client().post(
        "/api/accounts/ledger/movements/",
        {"account": account.id, "kind": "withdrawal", "amount": "-5"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "amount" in response.json()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_movement_create_404s_for_a_hidden_account():
    hidden = make_account("quiet", hidden=True)

    response = staff_client().post(
        "/api/accounts/ledger/movements/",
        {"account": hidden.id, "kind": "deposit", "amount": "10"},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert not FundMovement.objects.exists()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_movements_list_filters_by_account_and_404s_on_hidden():
    from apps.accounts.visibility import HIDDEN_VIEWER

    User.objects.create_user(HIDDEN_VIEWER, password="pw12345!", is_staff=True)
    client = staff_client()

    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    movement(visible, FundMovementType.DEPOSIT, "100")
    movement(hidden, FundMovementType.DEPOSIT, "5000")

    assert len(client.get("/api/accounts/ledger/movements/").json()) == 1
    assert client.get(f"/api/accounts/ledger/movements/?account={hidden.id}").status_code == 404

    viewer = Client()
    assert viewer.login(username=HIDDEN_VIEWER, password="pw12345!")
    assert len(viewer.get("/api/accounts/ledger/movements/").json()) == 2


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_delete_a_movement():
    account = make_account()
    row = movement(account, FundMovementType.DEPOSIT, "100")

    response = staff_client().delete(f"/api/accounts/ledger/movements/{row.id}/")
    assert response.status_code == 204
    assert not FundMovement.objects.exists()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_delete_404s_for_a_hidden_accounts_movement():
    hidden = make_account("quiet", hidden=True)
    row = movement(hidden, FundMovementType.DEPOSIT, "100")

    assert staff_client().delete(f"/api/accounts/ledger/movements/{row.id}/").status_code == 404
    assert FundMovement.objects.filter(id=row.id).exists()
