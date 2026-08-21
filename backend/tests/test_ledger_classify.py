"""Telling the trade apart from the investor, without asking anybody.

``apps.accounts.detection`` produces a number nobody explained. This suite pins
what ``apps.accounts.classify`` then does with it, and the reasoning is the same
one the fan-out is built on: **the platform trades every account at once**. So a
change that came from trading shows up across the set, and a change that shows
up on one account while its peers sat still is somebody moving their own money.

The rules are ordered, and the order is the point — an emptied account is a
withdrawal even though a trade just closed on it, and a residual with no trade
anywhere near it is a transfer even though the account has traded before. Each
test here is one rule winning over the ones below it.

What is booked matters as much as what is decided: attributing to the trade
writes *no* ``FundMovement``, because PnL is ``balance - net invested`` and
leaving capital alone is what makes the change land in PnL.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings
from django.utils import timezone

from apps.accounts import bookkeeping, classify, detection
from apps.accounts.classify import Reason
from apps.accounts.models import (
    DetectedMovement,
    DetectionStatus,
    FundMovement,
    FundMovementType,
    LedgerAction,
    LedgerEvent,
    MovementClass,
)
from apps.core.money import D
from tests.conftest import ledger_settings
from tests.test_ledger_detection import closed_leg, make_account, staff_client

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db


def sweep(*readings, at=None) -> detection.Sweep:
    """One balance pass over several accounts, as ``_save_balances`` runs it.

    Every reading shares a single instant, which is what makes "only this
    account moved" a statement about the same moment for all of them.
    """
    now = at or timezone.now()
    pass_ = detection.Sweep(at=now)
    for account, equity in readings:
        detection.observe(
            account, equity=D(equity), asset="USDT", flat=True, at=now, sweep=pass_
        )
        account.save(update_fields=list(detection.FIELDS))
    classify.resolve_sweep(pass_)
    for found in pass_.detections:
        found.refresh_from_db()
    return pass_


def seed(*accounts, equity: str = "1000", ago: timedelta = timedelta(hours=1)) -> None:
    """Give each account a cursor to be compared against."""
    sweep(*[(account, equity) for account in accounts], at=timezone.now() - ago)


def only(pass_: detection.Sweep) -> DetectedMovement:
    assert len(pass_.detections) == 1, [d.account.label for d in pass_.detections]
    return pass_.detections[0]


# --- the rules, in the order they win --------------------------------------


def test_an_emptied_account_is_a_withdrawal_even_right_after_a_trade():
    """The user's case: minutes after a close, the account goes to nothing.

    A trade that just closed is on record and explains its own PnL. Nobody
    trades their balance to zero, so what is left is the investor taking it.
    """
    account = make_account()
    seed(account)
    closed_leg(account, "50")
    found = only(sweep((account, "3")))

    assert found.suggested_class == MovementClass.INVESTOR
    assert found.classification_reason == Reason.EMPTIED
    assert found.suggested_kind == FundMovementType.WITHDRAWAL
    assert found.traded_in_window, "a trade did close in the window; it still lost"
    assert found.status == DetectionStatus.ACCEPTED
    assert D(FundMovement.objects.get(account=account).amount) == D("1047")


def test_an_empty_account_being_funded_is_a_deposit():
    account = make_account()
    seed(account, equity="0")
    found = only(sweep((account, "500")))

    assert found.classification_reason == Reason.FUNDED_FROM_EMPTY
    assert found.suggested_kind == FundMovementType.DEPOSIT
    assert D(FundMovement.objects.get(account=account).amount) == D("500")


def test_money_arriving_while_nothing_has_traded_came_from_outside():
    """No leg opened or closed anywhere near the window, so there is no trade
    for the money to have come from — the injection-before-the-trade case."""
    account = make_account()
    seed(account)
    found = only(sweep((account, "1500")))

    assert found.classification_reason == Reason.NO_TRADE
    assert found.suggested_class == MovementClass.INVESTOR
    assert not found.traded_in_window
    assert D(FundMovement.objects.get(account=account).amount) == D("500")


def test_a_trade_that_closed_just_before_the_window_still_counts_as_near():
    """Proximity, not containment. Balances are read every few seconds, so a
    close lands in one window and the fee that follows it in the next — and the
    next window would otherwise read as "nothing traded, must be a transfer"."""
    account = make_account()
    seed(account, ago=timedelta(minutes=1))
    closed_leg(account, "100", at=timezone.now() - timedelta(minutes=5))
    found = only(sweep((account, "1180")))

    assert found.traded_in_window
    assert found.classification_reason != Reason.NO_TRADE


def test_a_trade_long_finished_is_not_near_enough_to_explain_anything():
    """The other side of the same setting: an account that traded an hour ago
    counts as untraded now, so money arriving today is a transfer."""
    account = make_account()
    seed(account, ago=timedelta(minutes=1))
    closed_leg(account, "10", at=timezone.now() - timedelta(hours=2))
    found = only(sweep((account, "1400")))

    assert not found.traded_in_window
    assert found.classification_reason == Reason.NO_TRADE


def test_one_account_moving_while_its_peers_sit_still_is_the_investor():
    """The headline rule. Three accounts, one trade, one unexplained change.

    Every account closed the same trade and its PnL is on record. Two of them
    land exactly where that PnL says; the third is $400 richer, and a fan-out
    cannot enrich one leg alone.
    """
    a, b, c = make_account("a"), make_account("b"), make_account("c")
    seed(a, b, c)
    for account in (a, b, c):
        closed_leg(account, "50")
    found = only(sweep((a, "1450"), (b, "1050"), (c, "1050")))

    assert found.account_id == a.id
    assert found.classification_reason == Reason.ISOLATED
    assert found.suggested_class == MovementClass.INVESTOR
    assert (found.peers_observed, found.peers_moved) == (2, 0)
    assert D(FundMovement.objects.get(account=a).amount) == D("400")
    assert not FundMovement.objects.filter(account__in=[b, c]).exists()


def test_a_change_that_hits_every_account_at_once_is_the_trade():
    """Fees and funding the recorded PnL missed land on all of them together.

    Three investors do not transfer in the same second; a fan-out does — so the
    residual is the trade's, and no capital moves.
    """
    a, b, c = make_account("a"), make_account("b"), make_account("c")
    seed(a, b, c)
    for account in (a, b, c):
        closed_leg(account, "100")
    pass_ = sweep((a, "1080"), (b, "1078"), (c, "1081"))

    assert len(pass_.detections) == 3
    for found in pass_.detections:
        assert found.suggested_class == MovementClass.TRADE
        assert found.classification_reason == Reason.PORTFOLIO_WIDE
        assert found.peers_moved == 2
        assert found.status == DetectionStatus.ATTRIBUTED
    assert FundMovement.objects.count() == 0, "attributing to the trade books nothing"


def test_a_leftover_small_next_to_the_trades_own_pnl_is_the_trade():
    """One account, so isolation cannot be argued: size decides instead."""
    account = make_account()
    seed(account)
    closed_leg(account, "200")
    found = only(sweep((account, "1212")))

    assert found.classification_reason == Reason.TRADE_RESIDUAL
    assert found.suggested_class == MovementClass.TRADE
    assert FundMovement.objects.count() == 0


def test_an_unclear_change_defaults_to_the_trade_and_waits():
    """Nothing decided it: a big residual, one account, a trade in the window.

    The standing default applies — it was the trade — but it is not confident,
    so under ``safe`` the row is the one thing that reaches the panel's queue.
    """
    account = make_account()
    seed(account)
    closed_leg(account, "20")
    found = only(sweep((account, "1620")))

    assert found.suggested_class == MovementClass.TRADE
    assert found.classification_reason == Reason.UNCLEAR
    assert not found.confident
    assert found.status == DetectionStatus.PENDING


# --- how much the platform is allowed to decide by itself ------------------


@override_settings(LEDGER=ledger_settings(AUTO_RESOLVE="off"))
def test_off_classifies_but_resolves_nothing():
    account = make_account()
    seed(account)
    found = only(sweep((account, "1500")))

    assert found.suggested_class == MovementClass.INVESTOR
    assert found.confident
    assert found.status == DetectionStatus.PENDING, "the verdict is advice, not action"
    assert FundMovement.objects.count() == 0


@override_settings(LEDGER=ledger_settings(AUTO_RESOLVE="all"))
def test_all_acts_on_the_default_too():
    account = make_account()
    seed(account)
    closed_leg(account, "20")
    found = only(sweep((account, "1620")))

    assert not found.confident
    assert found.status == DetectionStatus.ATTRIBUTED
    assert found.auto_resolved


@override_settings(LEDGER=ledger_settings(CLASSIFY_ENABLED=False))
def test_classification_can_be_switched_off_entirely():
    account = make_account()
    seed(account)
    found = only(sweep((account, "1500")))

    assert found.status == DetectionStatus.PENDING
    assert found.classification_reason == ""


# --- what the decisions do to the books ------------------------------------


def test_attributing_to_the_trade_leaves_the_change_in_pnl():
    """The whole reason ``attribute`` is not ``dismiss``: PnL is balance minus
    invested capital, so booking nothing is what credits the trade."""
    from apps.accounts.ledger import account_ledger

    account = make_account(last_balance="1500")
    bookkeeping.create_movement(
        account=account, kind=FundMovementType.DEPOSIT, amount=D("1000"), actor="boss"
    )
    seed(account)
    closed_leg(account, "20")
    found = only(sweep((account, "1620")))
    bookkeeping.attribute_detection(found, actor="boss")

    row = account_ledger(account)
    assert D(row["net_invested"]) == D("1000")
    assert D(row["pnl"]) == D("500"), "the unexplained gain stayed in PnL"


def test_an_automatic_decision_can_be_reopened_and_takes_its_booking_with_it():
    account = make_account()
    seed(account)
    found = only(sweep((account, "1500")))
    assert found.status == DetectionStatus.ACCEPTED
    movement_id = found.movement_id

    bookkeeping.reopen_detection(found, actor="boss", note="that was a trade")
    found.refresh_from_db()

    assert found.status == DetectionStatus.PENDING
    assert found.movement_id is None
    assert not FundMovement.objects.filter(id=movement_id).exists()
    actions = list(
        LedgerEvent.objects.filter(account=account).values_list("action", flat=True)
    )
    assert LedgerAction.REOPENED in actions
    assert LedgerAction.DELETED in actions, "the reversal is on the record too"


def test_every_automatic_decision_names_the_rule_that_made_it():
    account = make_account()
    seed(account)
    found = only(sweep((account, "1500")))

    event = LedgerEvent.objects.filter(
        detection_id=found.id, action=LedgerAction.CREATED
    ).get()
    assert event.actor == "", "blank actor means the platform, not an operator"
    assert Reason.NO_TRADE in event.note


def test_a_resolved_detection_cannot_be_resolved_twice():
    account = make_account()
    seed(account)
    closed_leg(account, "100")
    found = only(sweep((account, "1105")))
    assert found.status == DetectionStatus.ATTRIBUTED

    with pytest.raises(ValueError):
        bookkeeping.attribute_detection(found, actor="boss")
    with pytest.raises(ValueError):
        bookkeeping.accept_detection(found, actor="boss")


# --- the panel's side ------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY], LEDGER=ledger_settings(AUTO_RESOLVE="off"))
def test_the_api_offers_both_answers_and_a_way_back():
    account = make_account()
    seed(account)
    closed_leg(account, "20")
    found = only(sweep((account, "1620")))
    client = staff_client()

    listed = client.get("/api/accounts/ledger/detections/").json()
    assert listed[0]["suggested_class"] == MovementClass.TRADE
    assert listed[0]["classification_reason"] == Reason.UNCLEAR
    assert listed[0]["confident"] is False

    url = f"/api/accounts/ledger/detections/{found.id}/"
    assert client.post(f"{url}attribute/", content_type="application/json").status_code == 200
    assert FundMovement.objects.count() == 0

    resolved = client.get("/api/accounts/ledger/detections/?status=resolved").json()
    assert [row["status"] for row in resolved] == [DetectionStatus.ATTRIBUTED]

    assert client.post(f"{url}reopen/", content_type="application/json").status_code == 200
    accepted = client.post(
        f"{url}accept/", data={"amount": "600"}, content_type="application/json"
    )
    assert accepted.status_code == 201
    assert D(FundMovement.objects.get().amount) == D("600")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_only_what_the_platform_could_not_call_is_left_waiting():
    """The point of the whole feature: the queue holds the exceptions."""
    a, b = make_account("a"), make_account("b")
    seed(a, b)
    for account in (a, b):
        closed_leg(account, "50")
    sweep((a, "1450"), (b, "1050"))
    client = staff_client()

    assert client.get("/api/accounts/ledger/detections/").json() == []
    decided = client.get("/api/accounts/ledger/detections/?status=resolved").json()
    assert [row["auto_resolved"] for row in decided] == [True]
    assert Decimal(decided[0]["amount"]) == D("400")
