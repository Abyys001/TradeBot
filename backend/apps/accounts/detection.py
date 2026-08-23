"""Telling a trade result apart from an investor moving money.

The exchange reports one number — equity — and three different things move it:

* **A. trade PnL** — the platform placed the order, so it already knows the
  figure: the closed legs it recorded itself.
* **B. a withdrawal** — money left, and no API can tell us (spec §7 keys are
  trade-only, they cannot read transfer history).
* **C. a capital injection** — money arrived, same blind spot.

So B and C are inferred by subtraction: whatever equity did that A, plus the
cash flows already on record, does not explain. The remainder is a
``DetectedMovement`` — a question, not yet an entry.

Two rules keep the subtraction honest:

**Only compare flat to flat.** Equity carries unrealised PnL, so while a
position is open it moves with the market and every tick would read as a
deposit. The cursor therefore only advances on a reading taken while the account
holds no open leg, and both ends of every window are such a reading.

**Never propose against an unknown start.** An account with no cursor yet is
seeded silently. The ledger starts from now, exactly as the manual one does.

What the remainder *was* — the trade, or somebody's cash — is not decided here.
This module only measures; ``apps.accounts.classify`` reads the whole sweep and
calls it, because "only this account moved" is a fact about the set of accounts
and cannot be seen one row at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import (
    DetectedMovement,
    FundMovementType,
    LedgerAction,
    LedgerEvent,
)
from apps.core.money import ZERO, D
from apps.logging.utils import system_log

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

    from apps.accounts.models import ConnectedAccount


@dataclass
class Sweep:
    """One pass over every account's balance, as the classifier needs it.

    ``observed`` is the part that cannot be reconstructed afterwards: the
    accounts that were readable, in USDT and flat at this instant — the ones
    whose silence is evidence. An account that failed its balance read, or that
    is holding a position, is absent from both sets, because it did not say
    anything either way and silence proves nothing (the ``NEVER_SENT_CODES``
    rule, applied to money).
    """

    at: datetime
    observed: set[int] = field(default_factory=set)
    detections: list[DetectedMovement] = field(default_factory=list)


def threshold(equity: Decimal, exchange: str = "") -> Decimal:
    """How far equity may drift before it counts as a cash flow.

    Fees, funding and the exchange's own rounding move equity by small amounts
    that belong to no deposit and to no trade. The floor is absolute so a tiny
    account is not swamped by it, and proportional so a large one is not buried
    in proposals for rounding dust; the larger of the two wins.

    Q28: the pair is read **per exchange** first. What is being measured differs
    by venue — a perpetual venue pays funding several times a day and a spot
    venue pays none — so one global percentage either hides real transfers on
    spot or proposes funding as a withdrawal on perps. An exchange with no
    override falls back to the global pair, which is what every venue used
    before and what an untuned one still uses.
    """
    config = settings.LEDGER
    override = config["DETECT_PER_EXCHANGE"].get(exchange, {}) if exchange else {}
    floor = D(override.get("DETECT_MIN_USDT", config["DETECT_MIN_USDT"]))
    pct = D(override.get("DETECT_MIN_PCT", config["DETECT_MIN_PCT"]))
    proportional = abs(equity) * pct / Decimal("100")
    return max(floor, proportional)


def _closed_trade_pnl(account: ConnectedAccount, since: datetime, until: datetime) -> Decimal:
    """Reading A: what the platform's own closed legs explain in this window.

    Legs are counted by ``closed_at`` because that is when the exchange settles
    the result into equity — a leg opened before the window and closed inside it
    moved the number inside it.
    """
    from apps.trading.models import TradeLeg

    total = ZERO
    rows = TradeLeg.objects.filter(
        account=account,
        ok=True,
        pnl__isnull=False,
        closed_at__gt=since,
        closed_at__lte=until,
    ).values_list("pnl", flat=True)
    for pnl in rows:
        total += D(pnl)
    return total


def _recorded_cash(account: ConnectedAccount, since: datetime, until: datetime) -> Decimal:
    """Cash flows already on record in this window, netted (deposits positive).

    Without this the detector would propose a second entry for a deposit the
    admin had already typed in — the equity moved, and the trades do not explain
    it, but the record does.
    """
    net = ZERO
    rows = account.fund_movements.filter(
        occurred_at__gt=since, occurred_at__lte=until
    ).values_list("kind", "amount")
    for kind, amount in rows:
        value = D(amount)
        net += value if kind == FundMovementType.DEPOSIT else -value
    return net


def observe(
    account: ConnectedAccount,
    *,
    equity: Decimal,
    asset: str,
    flat: bool,
    at: datetime | None = None,
    sweep: Sweep | None = None,
) -> DetectedMovement | None:
    """Record one equity reading and, if it is unexplained, propose a movement.

    Returns the proposal, or ``None`` when there is nothing to propose — which
    is the ordinary case: a reading that the closed trades account for, a
    reading taken while a position is open, or the very first reading.

    The caller is responsible for saving ``account``; the fields written here
    are named in ``FIELDS`` so a ``bulk_update`` can carry them.

    ``sweep`` collects what the whole pass saw, so ``classify.resolve_sweep``
    can tell an account that moved alone from one that moved with the others.
    Pass it from a caller that reads every account at once; without it the rows
    are still created, just left for a person to classify.
    """
    now = at or timezone.now()
    account.last_equity = equity

    if not settings.LEDGER["DETECT_ENABLED"]:
        return None
    # Q4: a non-USDT account is reported, not traded and not banked. Subtracting
    # USDT trade PnL from a BTC-denominated equity would be arithmetic on two
    # different units.
    if (asset or "").upper() != "USDT":
        return None
    if not flat:
        return None

    previous = account.ledger_cursor_equity
    since = account.ledger_cursor_at
    account.ledger_cursor_equity = equity
    account.ledger_cursor_at = now
    if sweep is not None:
        sweep.observed.add(account.id)
    if previous is None or since is None:
        return None

    previous = D(previous)
    delta = equity - previous
    trade_pnl = _closed_trade_pnl(account, since, now)
    manual_net = _recorded_cash(account, since, now)
    unexplained = delta - trade_pnl - manual_net

    if abs(unexplained) < threshold(equity, account.exchange):
        return None

    detection = DetectedMovement.objects.create(
        account=account,
        previous_equity=previous,
        current_equity=equity,
        delta=delta,
        trade_pnl=trade_pnl,
        manual_net=manual_net,
        unexplained=unexplained,
        suggested_kind=(
            FundMovementType.DEPOSIT if unexplained > ZERO else FundMovementType.WITHDRAWAL
        ),
        asset="USDT",
        window_start=since,
        observed_at=now,
    )
    LedgerEvent.objects.create(
        actor="",
        action=LedgerAction.DETECTED,
        account=account,
        account_label=account.label,
        detection_id=detection.id,
        kind=detection.suggested_kind,
        amount=detection.amount,
        after={
            "previous_equity": str(previous),
            "current_equity": str(equity),
            "delta": str(delta),
            "trade_pnl": str(trade_pnl),
            "manual_net": str(manual_net),
            "unexplained": str(unexplained),
        },
        note="awaiting review",
    )
    system_log(
        "WARNING",
        "ADMIN",
        (
            f"Unexplained balance change on {account.label}: equity moved "
            f"{delta:+} USDT, closed trades explain {trade_pnl:+}, recorded cash "
            f"{manual_net:+}, leaving {unexplained:+} unaccounted for"
        ),
        source="apps.accounts.detection",
        account_id=account.id,
        exchange=account.exchange,
    )
    if sweep is not None:
        sweep.detections.append(detection)
    return detection


#: The account fields ``observe`` writes. Named so callers batching a save can
#: list them without guessing.
FIELDS = ("last_equity", "ledger_cursor_equity", "ledger_cursor_at")
