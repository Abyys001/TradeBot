"""Every write to the money record, and the audit trail that comes with it.

One module owns creating, editing and deleting a ``FundMovement`` and resolving
a ``DetectedMovement``, for one reason: each of those changes what an investor's
capital is recorded as, and each must leave a ``LedgerEvent`` behind saying who
did it and what the value was before. Scattering the writes across views would
scatter the trail with them, and a trail with holes in it is not a trail.

The trail is append-only by convention — nothing here updates or deletes a
``LedgerEvent``. Deleting a movement writes an event; the event outlives it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    DetectedMovement,
    DetectionStatus,
    FundMovement,
    FundMovementSource,
    LedgerAction,
    LedgerEvent,
)
from apps.core.money import D
from apps.logging.utils import system_log

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

    from apps.accounts.models import ConnectedAccount

#: The movement fields an operator may change after the fact. The account is
#: not among them: moving a recorded flow to a different account rewrites two
#: accounts' invested capital at once, and is better done as a delete plus a
#: fresh entry, which leaves two legible events instead of one ambiguous one.
EDITABLE = ("kind", "amount", "asset", "occurred_at", "note")


#: Movement amounts are stored at 8dp. A freshly built instance still carries
#: whatever Python object was assigned to it, so a before/after comparison would
#: read ``100`` against ``100.00000000`` and call an untouched field changed.
#: Every snapshot is quantised to the column's precision first.
CENTS = Decimal("0.00000001")


def _snapshot(movement: FundMovement) -> dict[str, Any]:
    return {
        "kind": movement.kind,
        "amount": str(D(movement.amount).quantize(CENTS)),
        "asset": movement.asset,
        "occurred_at": movement.occurred_at.isoformat(),
        "note": movement.note,
    }


def _log(event: LedgerEvent, verb: str) -> None:
    system_log(
        "INFO",
        "ADMIN",
        (
            f"{event.actor or 'platform'} {verb} {event.kind} of "
            f"{event.amount} on {event.account_label}"
        ),
        source="apps.accounts.bookkeeping",
        account_id=event.account_id,
        context={"before": event.before, "after": event.after, "note": event.note},
    )


def _event(
    *,
    actor: str,
    action: str,
    account: ConnectedAccount,
    movement: FundMovement | None = None,
    detection: DetectedMovement | None = None,
    kind: str = "",
    amount: Decimal | None = None,
    before: dict | None = None,
    after: dict | None = None,
    note: str = "",
) -> LedgerEvent:
    return LedgerEvent.objects.create(
        actor=actor,
        action=action,
        account=account,
        account_label=account.label,
        movement_id=movement.id if movement is not None else None,
        detection_id=detection.id if detection is not None else None,
        kind=kind,
        amount=amount,
        before=before,
        after=after,
        note=note[:200],
    )


@transaction.atomic
def create_movement(
    *,
    account: ConnectedAccount,
    kind: str,
    amount: Decimal,
    actor: str,
    asset: str = "USDT",
    occurred_at: datetime | None = None,
    note: str = "",
    source: str = FundMovementSource.MANUAL,
    detection: DetectedMovement | None = None,
) -> FundMovement:
    movement = FundMovement.objects.create(
        account=account,
        kind=kind,
        amount=amount,
        asset=asset,
        occurred_at=occurred_at or timezone.now(),
        note=note,
        source=source,
        created_by=actor,
        updated_by=actor,
    )
    event = _event(
        actor=actor,
        action=LedgerAction.CREATED,
        account=account,
        movement=movement,
        detection=detection,
        kind=kind,
        amount=amount,
        after=_snapshot(movement),
        note=note,
    )
    _log(event, "recorded a")
    return movement


@transaction.atomic
def edit_movement(
    movement: FundMovement, *, actor: str, changes: dict[str, Any]
) -> FundMovement:
    """Apply ``changes`` and record what the values were before.

    Only the fields that actually moved go into the event — an edit that
    retyped the same amount should not read as a change to it.
    """
    before = _snapshot(movement)
    for field in EDITABLE:
        if field in changes:
            setattr(movement, field, changes[field])
    movement.updated_by = actor
    movement.save()

    after = _snapshot(movement)
    moved = {key: value for key, value in after.items() if before[key] != value}
    if not moved:
        return movement

    event = _event(
        actor=actor,
        action=LedgerAction.EDITED,
        account=movement.account,
        movement=movement,
        kind=movement.kind,
        amount=movement.amount,
        before={key: before[key] for key in moved},
        after=moved,
        note=movement.note,
    )
    _log(event, "edited a")
    return movement


@transaction.atomic
def delete_movement(movement: FundMovement, *, actor: str) -> None:
    before = _snapshot(movement)
    account = movement.account
    movement_id = movement.id
    movement.delete()
    event = LedgerEvent.objects.create(
        actor=actor,
        action=LedgerAction.DELETED,
        account=account,
        account_label=account.label,
        movement_id=movement_id,
        kind=before["kind"],
        amount=Decimal(before["amount"]),
        before=before,
        note=before["note"][:200],
    )
    _log(event, "deleted a")


@transaction.atomic
def accept_detection(
    detection: DetectedMovement,
    *,
    actor: str,
    kind: str | None = None,
    amount: Decimal | None = None,
    occurred_at: datetime | None = None,
    note: str = "",
    auto: bool = False,
) -> FundMovement:
    """Turn a proposal into a real cash flow, with the operator's corrections.

    The proposal is a starting point, not a verdict: the operator may change the
    direction and the figure — the platform inferred both by subtraction, and
    the person who moved the money knows better than the arithmetic does.

    ``auto`` marks a booking the classifier made by itself. The row is written
    identically either way — the flag is there so the panel can show which
    decisions nobody has looked at, and so ``reopen_detection`` has something to
    undo.
    """
    if detection.status != DetectionStatus.PENDING:
        raise ValueError("this detection has already been resolved")

    movement = create_movement(
        account=detection.account,
        kind=kind or detection.suggested_kind,
        amount=amount if amount is not None else detection.amount,
        actor=actor,
        asset=detection.asset,
        occurred_at=occurred_at or detection.observed_at,
        note=note,
        source=FundMovementSource.DETECTED,
        detection=detection,
    )
    edited = (kind is not None and kind != detection.suggested_kind) or (
        amount is not None and amount != detection.amount
    )
    detection.status = DetectionStatus.ACCEPTED
    detection.resolved_at = timezone.now()
    detection.resolved_by = actor
    detection.movement = movement
    detection.auto_resolved = auto
    detection.save(
        update_fields=["status", "resolved_at", "resolved_by", "movement", "auto_resolved"]
    )

    event = _event(
        actor=actor,
        action=LedgerAction.ACCEPTED,
        account=detection.account,
        movement=movement,
        detection=detection,
        kind=movement.kind,
        amount=movement.amount,
        before={
            "suggested_kind": detection.suggested_kind,
            "suggested_amount": str(detection.amount),
        },
        after=_snapshot(movement),
        note=note or ("corrected on accept" if edited else "accepted as proposed"),
    )
    _log(event, "accepted a detected")
    return movement


@transaction.atomic
def attribute_detection(
    detection: DetectedMovement, *, actor: str, note: str = "", auto: bool = False
) -> DetectedMovement:
    """Resolve a proposal as the trade's own doing. Nothing is booked.

    This is not a dismissal, and the difference matters to the numbers. PnL is
    ``current balance - net invested`` (``apps.accounts.ledger``), so a change
    attributed to trading needs no entry at all: leaving invested capital alone
    is exactly what makes the move land in PnL, which is where a trade result
    belongs. Booking it as a deposit instead would hide a win; booking a real
    deposit here would show one that never happened.
    """
    if detection.status != DetectionStatus.PENDING:
        raise ValueError("this detection has already been resolved")

    detection.status = DetectionStatus.ATTRIBUTED
    detection.resolved_at = timezone.now()
    detection.resolved_by = actor
    detection.auto_resolved = auto
    detection.save(
        update_fields=["status", "resolved_at", "resolved_by", "auto_resolved"]
    )
    event = _event(
        actor=actor,
        action=LedgerAction.ATTRIBUTED,
        account=detection.account,
        detection=detection,
        kind="",
        amount=detection.amount,
        before={
            "suggested_kind": detection.suggested_kind,
            "suggested_amount": str(detection.amount),
        },
        after={"classification": "trade", "reason": detection.classification_reason},
        note=note,
    )
    _log(event, "attributed to trading a")
    return detection


@transaction.atomic
def reopen_detection(
    detection: DetectedMovement, *, actor: str, note: str = ""
) -> DetectedMovement:
    """Undo a resolution and put the row back in the queue.

    The classifier decides by itself (``apps.accounts.classify``), so there has
    to be a way back: a verdict nobody can overturn is worse than the manual
    queue it replaced. A booking it made is deleted through ``delete_movement``,
    which means the reversal leaves its own event rather than quietly erasing
    the first one.
    """
    if detection.status == DetectionStatus.PENDING:
        return detection

    movement = detection.movement
    detection.status = DetectionStatus.PENDING
    detection.resolved_at = None
    detection.resolved_by = ""
    detection.auto_resolved = False
    detection.movement = None
    detection.save(
        update_fields=["status", "resolved_at", "resolved_by", "auto_resolved", "movement"]
    )
    if movement is not None:
        delete_movement(movement, actor=actor)

    event = _event(
        actor=actor,
        action=LedgerAction.REOPENED,
        account=detection.account,
        detection=detection,
        kind=detection.suggested_kind,
        amount=detection.amount,
        note=note,
    )
    _log(event, "reopened a resolved")
    return detection


@transaction.atomic
def dismiss_detection(
    detection: DetectedMovement, *, actor: str, note: str = ""
) -> DetectedMovement:
    """Reject a proposal. Nothing enters the ledger; the reason is kept."""
    if detection.status != DetectionStatus.PENDING:
        raise ValueError("this detection has already been resolved")

    detection.status = DetectionStatus.DISMISSED
    detection.resolved_at = timezone.now()
    detection.resolved_by = actor
    detection.save(update_fields=["status", "resolved_at", "resolved_by"])
    event = _event(
        actor=actor,
        action=LedgerAction.DISMISSED,
        account=detection.account,
        detection=detection,
        kind=detection.suggested_kind,
        amount=detection.amount,
        before={
            "suggested_kind": detection.suggested_kind,
            "suggested_amount": str(detection.amount),
        },
        note=note,
    )
    _log(event, "dismissed a detected")
    return detection


def record_split_change(*, before: dict[str, str], after: dict[str, str], actor: str) -> None:
    """The split decides who is owed what, so a change to it is an audit event."""
    if before == after:
        return
    LedgerEvent.objects.create(
        actor=actor,
        action=LedgerAction.SPLIT,
        account=None,
        account_label="",
        before=before,
        after=after,
    )
    system_log(
        "WARNING",
        "ADMIN",
        f"{actor} changed the profit split: {before} -> {after}",
        source="apps.accounts.bookkeeping",
    )
