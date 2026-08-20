"""Telling trade PnL apart from an investor's cash, and auditing the answer.

The detector (``apps.accounts.detection``) subtracts what the platform already
knows — the legs it closed itself, plus the cash flows on record — from what the
exchange's equity did. Everything left over is proposed as a deposit or a
withdrawal and waits for a person. These tests pin the three things that make
that safe: it never proposes against an unknown start, it never compares across
an open position, and nothing it proposes reaches the ledger unaccepted.

``apps.accounts.bookkeeping`` is the other half: every change to the money
record leaves a ``LedgerEvent`` naming who made it and what the value was
before.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts import bookkeeping, detection
from apps.accounts.models import (
    AccountStatus,
    ConnectedAccount,
    DetectedMovement,
    DetectionStatus,
    Exchange,
    FundMovement,
    FundMovementSource,
    FundMovementType,
    LedgerAction,
    LedgerEvent,
)
from apps.core.money import D
from apps.trading.models import Trade, TradeLeg, TradeStatus

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db


def make_account(label: str = "partner-a", **overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=overrides.pop("exchange", Exchange.PAPER),
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


def staff_client(username: str = "boss") -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"is_staff": True})
    user.set_password("pw12345!")
    user.is_staff = True
    user.save()
    client = Client()
    assert client.login(username=username, password="pw12345!")
    return client


def observe(account: ConnectedAccount, equity: str, *, flat: bool = True, at=None):
    """One balance reading, saved the way ``_save_balances`` saves it."""
    result = detection.observe(
        account, equity=D(equity), asset="USDT", flat=flat, at=at or timezone.now()
    )
    account.save(update_fields=list(detection.FIELDS))
    return result


def closed_leg(account: ConnectedAccount, pnl: str, *, at=None) -> TradeLeg:
    trade = Trade.objects.create(
        symbol="BTCUSDT", side="long", leverage=10, status=TradeStatus.CLOSED
    )
    return TradeLeg.objects.create(
        trade=trade,
        account=account,
        ok=True,
        pnl=D(pnl),
        closed_at=at or timezone.now(),
    )


# --- the detector ----------------------------------------------------------


def test_the_first_reading_seeds_the_cursor_and_proposes_nothing():
    """No history behind a number means no claim can be made about it."""
    account = make_account()
    assert observe(account, "1000") is None
    account.refresh_from_db()
    assert account.ledger_cursor_equity == D("1000")
    assert account.ledger_cursor_at is not None
    assert DetectedMovement.objects.count() == 0


def test_a_gain_the_closed_trades_explain_is_not_a_cash_flow():
    """Reading A: the platform placed the order, so it knows the figure."""
    account = make_account()
    start = timezone.now() - timedelta(hours=2)
    observe(account, "1000", at=start)
    closed_leg(account, "120", at=start + timedelta(hours=1))

    assert observe(account, "1120") is None
    assert DetectedMovement.objects.count() == 0


def test_money_arriving_with_no_trade_behind_it_proposes_a_deposit():
    """Reading C: equity rose, nothing the platform did explains it."""
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))

    proposal = observe(account, "1500")

    assert proposal is not None
    assert proposal.suggested_kind == FundMovementType.DEPOSIT
    assert proposal.amount == D("500")
    assert proposal.status == DetectionStatus.PENDING
    assert proposal.trade_pnl == D("0")


def test_money_leaving_with_no_trade_behind_it_proposes_a_withdrawal():
    """Reading B: the mirror case, and the one that must never be silent."""
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))

    proposal = observe(account, "700")

    assert proposal is not None
    assert proposal.suggested_kind == FundMovementType.WITHDRAWAL
    assert proposal.amount == D("300")


def test_only_the_part_the_trades_cannot_explain_is_proposed():
    """A and C in the same window: the subtraction has to separate them."""
    account = make_account()
    start = timezone.now() - timedelta(hours=2)
    observe(account, "1000", at=start)
    closed_leg(account, "100", at=start + timedelta(minutes=30))

    proposal = observe(account, "1600")

    assert proposal is not None
    assert proposal.trade_pnl == D("100")
    assert proposal.unexplained == D("500")
    assert proposal.suggested_kind == FundMovementType.DEPOSIT


def test_a_deposit_already_typed_in_is_not_proposed_a_second_time():
    """The record explains it even though no trade does."""
    account = make_account()
    start = timezone.now() - timedelta(hours=2)
    observe(account, "1000", at=start)
    FundMovement.objects.create(
        account=account,
        kind=FundMovementType.DEPOSIT,
        amount=D("500"),
        occurred_at=start + timedelta(minutes=10),
    )

    assert observe(account, "1500") is None


def test_an_open_position_never_moves_the_cursor():
    """Equity carries unrealised PnL; a market swing is not a cash flow."""
    account = make_account()
    start = timezone.now() - timedelta(hours=2)
    observe(account, "1000", at=start)

    assert observe(account, "1400", flat=False) is None
    account.refresh_from_db()
    assert account.ledger_cursor_equity == D("1000"), "the cursor moved mid-trade"
    # ...and the equity is still recorded, so the panel can show it.
    assert account.last_equity == D("1400")

    # Flat again, with the round trip closed at a profit: fully explained.
    closed_leg(account, "400", at=timezone.now())
    assert observe(account, "1400") is None


@override_settings(
    LEDGER={"DETECT_ENABLED": True, "DETECT_MIN_USDT": "1", "DETECT_MIN_PCT": "0.25"}
)
def test_fees_and_funding_dust_stays_below_the_threshold():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    # 0.25% of 1000 is 2.50, which beats the $1 floor.
    assert observe(account, "998.20") is None
    account.refresh_from_db()
    assert account.ledger_cursor_equity == D("998.20"), "the cursor must still advance"


@override_settings(
    LEDGER={"DETECT_ENABLED": False, "DETECT_MIN_USDT": "1", "DETECT_MIN_PCT": "0.25"}
)
def test_the_detector_can_be_switched_off_entirely():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    assert observe(account, "5000") is None
    assert DetectedMovement.objects.count() == 0


def test_a_non_usdt_account_is_never_measured_in_dollars():
    """Q4: reported, not traded — and not banked either."""
    account = make_account(last_balance_asset="BTC")
    detection.observe(account, equity=D("2"), asset="BTC", flat=True)
    detection.observe(account, equity=D("5"), asset="BTC", flat=True)
    assert DetectedMovement.objects.count() == 0
    assert account.last_equity == D("5")


def test_a_detection_writes_its_own_audit_entry():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    observe(account, "1500")

    event = LedgerEvent.objects.get(action=LedgerAction.DETECTED)
    assert event.actor == "", "the platform is not an operator"
    assert event.amount == D("500")
    assert event.after["delta"] == "500"


# --- accepting, editing, and the trail -------------------------------------


def test_nothing_proposed_reaches_the_ledger_until_someone_accepts_it():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    proposal = observe(account, "1500")

    assert FundMovement.objects.count() == 0

    movement = bookkeeping.accept_detection(proposal, actor="boss")

    assert movement.source == FundMovementSource.DETECTED
    assert movement.amount == D("500")
    assert movement.created_by == "boss"
    proposal.refresh_from_db()
    assert proposal.status == DetectionStatus.ACCEPTED
    assert proposal.movement_id == movement.id


def test_a_proposal_can_be_corrected_on_the_way_in():
    """The arithmetic inferred it; the person who moved the money knows."""
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    proposal = observe(account, "1500")

    movement = bookkeeping.accept_detection(
        proposal, actor="boss", amount=D("480"), note="fee on the transfer"
    )

    assert movement.amount == D("480")
    event = LedgerEvent.objects.get(action=LedgerAction.ACCEPTED)
    assert event.before["suggested_amount"] == "500"
    assert event.after["amount"] == "480.00000000"


def test_a_dismissed_proposal_books_nothing_and_cannot_be_resolved_twice():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    proposal = observe(account, "700")

    bookkeeping.dismiss_detection(proposal, actor="boss", note="exchange promo clawback")

    assert FundMovement.objects.count() == 0
    assert LedgerEvent.objects.filter(action=LedgerAction.DISMISSED).exists()
    with pytest.raises(ValueError):
        bookkeeping.accept_detection(proposal, actor="boss")


def test_an_edit_records_only_what_actually_changed():
    account = make_account()
    movement = bookkeeping.create_movement(
        account=account, kind=FundMovementType.DEPOSIT, amount=D("100"), actor="boss"
    )

    bookkeeping.edit_movement(
        movement, actor="alice", changes={"amount": D("250"), "note": "corrected"}
    )

    event = LedgerEvent.objects.get(action=LedgerAction.EDITED)
    assert event.actor == "alice"
    assert event.before == {"amount": "100.00000000", "note": ""}
    assert event.after == {"amount": "250.00000000", "note": "corrected"}
    movement.refresh_from_db()
    assert movement.created_by == "boss" and movement.updated_by == "alice"


def test_re_saving_the_same_values_is_not_an_edit():
    account = make_account()
    movement = bookkeeping.create_movement(
        account=account, kind=FundMovementType.DEPOSIT, amount=D("100"), actor="boss"
    )
    bookkeeping.edit_movement(movement, actor="boss", changes={"amount": D("100")})
    assert not LedgerEvent.objects.filter(action=LedgerAction.EDITED).exists()


def test_a_deleted_movement_leaves_its_record_behind():
    """The trail has to survive the row — a deletion is worth keeping."""
    account = make_account()
    movement = bookkeeping.create_movement(
        account=account,
        kind=FundMovementType.WITHDRAWAL,
        amount=D("75"),
        actor="boss",
        note="typo",
    )
    movement_id = movement.id

    bookkeeping.delete_movement(movement, actor="boss")

    assert not FundMovement.objects.filter(id=movement_id).exists()
    event = LedgerEvent.objects.get(action=LedgerAction.DELETED)
    assert event.movement_id == movement_id
    assert event.before["amount"] == "75.00000000"
    assert event.account_label == "partner-a"


# --- the API ---------------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_api_lists_pending_detections_and_resolves_them():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    proposal = observe(account, "1500")
    client = staff_client()

    rows = client.get("/api/accounts/ledger/detections/").json()
    assert [row["id"] for row in rows] == [proposal.id]
    assert rows[0]["suggested_kind"] == "deposit"
    assert Decimal(rows[0]["amount"]) == Decimal("500")

    response = client.post(
        f"/api/accounts/ledger/detections/{proposal.id}/accept/",
        {"amount": "500"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["source"] == "detected"

    # Resolved once, refused twice.
    again = client.post(
        f"/api/accounts/ledger/detections/{proposal.id}/accept/",
        {},
        content_type="application/json",
    )
    assert again.status_code == 409
    assert client.get("/api/accounts/ledger/detections/").json() == []


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_api_edits_a_movement_and_names_who_did_it():
    account = make_account()
    client = staff_client()
    created = client.post(
        "/api/accounts/ledger/movements/",
        {"account": account.id, "kind": "deposit", "amount": "100"},
        content_type="application/json",
    ).json()

    response = client.patch(
        f"/api/accounts/ledger/movements/{created['id']}/",
        {"amount": "180", "note": "bank fee was double counted"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert Decimal(response.json()["amount"]) == Decimal("180")
    assert response.json()["updated_by"] == "boss"

    events = client.get("/api/accounts/ledger/events/").json()
    assert [event["action"] for event in events] == ["edited", "created"]
    assert events[0]["actor"] == "boss"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_changing_the_split_is_an_audited_event():
    make_account()
    client = staff_client()

    response = client.post(
        "/api/accounts/ledger/split/",
        {"investor": "50", "trader": "30", "programmer": "20"},
        content_type="application/json",
    )

    assert response.status_code == 200
    event = LedgerEvent.objects.get(action=LedgerAction.SPLIT)
    assert event.actor == "boss"
    assert event.before["investor"] == "60.00"
    assert event.after["investor"] == "50.00"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_snapshot_counts_what_is_waiting_for_an_answer():
    account = make_account()
    observe(account, "1000", at=timezone.now() - timedelta(hours=1))
    observe(account, "1500")
    client = staff_client()

    assert client.get("/api/accounts/ledger/").json()["pending_detections"] == 1
