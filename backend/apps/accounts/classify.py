"""Deciding *what* an unexplained balance change was, without asking a person.

``apps.accounts.detection`` answers "how much of this equity move is left over
after the trades and the record explain what they can". This module answers the
question that follows, and the only one an operator actually cares about: was
that leftover **the trade**, or was it **somebody's cash**?

The exchange will never tell us — spec §7 keys are trade-only, so there is no
transfer history to read. But the platform knows something the exchange does
not: it placed the trade itself, on *every* account at once. That is the whole
lever here.

**A trade moves all of them. A transfer moves one.** An entry fans out to every
eligible account (spec §4) and closes the same way, so a change that came from
trading shows up across the set. An investor funding or emptying their own
account touches that account and nothing else. So the strongest signal is not
the size of the number — it is how many peers moved with it.

The rules, in the order they are tried:

1. **The account was emptied** — equity fell to nothing. Nobody trades to
   exactly zero; somebody withdrew.
2. **The account was filled from empty** — it had nothing and now has money.
3. **Nothing traded** — no leg opened or closed anywhere near the window, so
   there is no trade for the money to have come from.
4. **Isolated** — peers were readable, flat, and did not move. This one did.
5. **Portfolio-wide** — peers moved the same way in the same sweep. N investors
   do not transfer in the same second; a fan-out does.
6. **Trade residual** — the leftover is small next to the PnL of a trade that
   did close in the window: fees, funding, the exchange's own rounding.
7. **Nothing decided it** — the standing default. A balance that moves on a
   trading account moved because of the trade unless something says otherwise.

Rules 1-6 are *confident*: the platform acts on them. Rule 7 is not, and under
the default ``LEDGER_AUTO_RESOLVE=safe`` it is the only thing that reaches the
panel's queue. Every decision, automatic or not, is a ``LedgerEvent`` with the
reason on it and can be reopened — an automatic verdict nobody can overturn
would be worse than the manual queue it replaces.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import DetectionStatus, MovementClass
from apps.core.money import ZERO, D

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

    from apps.accounts.detection import Sweep
    from apps.accounts.models import DetectedMovement


class Reason:
    """Why the classifier decided what it did. Codes, translated in the panel."""

    EMPTIED = "emptied"
    FUNDED_FROM_EMPTY = "funded_from_empty"
    NO_TRADE = "no_trade"
    ISOLATED = "isolated"
    PORTFOLIO_WIDE = "portfolio_wide"
    TRADE_RESIDUAL = "trade_residual"
    UNCLEAR = "unclear"


class Verdict(NamedTuple):
    kind: str  # MovementClass
    reason: str
    confident: bool


#: The standing default (see the module docstring). Deliberately not "unknown":
#: attributing to the trade books nothing, so it is the reading that leaves the
#: record untouched when the platform genuinely cannot tell.
DEFAULT = Verdict(MovementClass.TRADE, Reason.UNCLEAR, confident=False)


def _cfg(key: str) -> Decimal:
    return D(settings.LEDGER[key])


def _near_zero(equity: Decimal, reference: Decimal) -> bool:
    """Is this equity indistinguishable from an empty account?

    Proportional to where the account started, because "empty" on a $100k
    account is not the same number of cents as on a $50 one, and an exchange
    leaves dust behind on a full withdrawal.
    """
    pct = _cfg("EMPTY_PCT") / Decimal("100")
    return abs(equity) <= max(abs(reference) * pct, _cfg("DETECT_MIN_USDT"))


def classify(
    detection: DetectedMovement,
    *,
    peers_observed: int,
    peers_moved: int,
    traded: bool,
) -> Verdict:
    """One detection's verdict. Pure: every input is already gathered."""
    previous = D(detection.previous_equity)
    current = D(detection.current_equity)
    unexplained = D(detection.unexplained)

    if unexplained < ZERO and _near_zero(current, previous):
        return Verdict(MovementClass.INVESTOR, Reason.EMPTIED, True)
    if unexplained > ZERO and _near_zero(previous, current):
        return Verdict(MovementClass.INVESTOR, Reason.FUNDED_FROM_EMPTY, True)
    if not traded:
        return Verdict(MovementClass.INVESTOR, Reason.NO_TRADE, True)
    if peers_observed and not peers_moved:
        return Verdict(MovementClass.INVESTOR, Reason.ISOLATED, True)
    if peers_moved:
        return Verdict(MovementClass.TRADE, Reason.PORTFOLIO_WIDE, True)

    tolerance = abs(D(detection.trade_pnl)) * _cfg("TRADE_TOLERANCE_PCT") / Decimal("100")
    if tolerance and abs(unexplained) <= tolerance:
        return Verdict(MovementClass.TRADE, Reason.TRADE_RESIDUAL, True)

    return DEFAULT


def _traded_accounts(account_ids: list[int], since: datetime, until: datetime) -> set[int]:
    """Which of these accounts had a leg open or close near the window.

    One query for the whole sweep. ``since`` is already widened by
    ``TRADE_WINDOW_SECONDS`` — the point is proximity, not containment: money
    that leaves minutes after a close is still "around" that trade, and money
    that arrives while nothing has traded for hours is not.
    """
    from django.db.models import Q

    from apps.trading.models import TradeLeg

    rows = TradeLeg.objects.filter(
        Q(closed_at__gte=since, closed_at__lte=until)
        | Q(opened_at__gte=since, opened_at__lte=until),
        account_id__in=account_ids,
        ok=True,
    ).values_list("account_id", flat=True)
    return set(rows)


def _sign(value: Decimal) -> int:
    return 1 if value > ZERO else -1


def resolve_sweep(sweep: Sweep) -> list[DetectedMovement]:
    """Classify everything one balance sweep proposed, and act on it.

    The whole sweep is handled at once because rules 4 and 5 are about the
    *set*: "only this account moved" is not a fact about one row. One sweep
    reads every account at a single instant (``services._save_balances``), so
    the cohort is exactly the rows here plus the accounts that were readable and
    had nothing to propose.

    Returns the detections it touched, each with its verdict written on it.
    """
    if not sweep.detections or not settings.LEDGER["CLASSIFY_ENABLED"]:
        return []

    window = timezone.timedelta(seconds=float(_cfg("TRADE_WINDOW_SECONDS")))
    starts = [d.window_start for d in sweep.detections if d.window_start]
    since = (min(starts) if starts else sweep.at) - window
    traded = _traded_accounts([d.account_id for d in sweep.detections], since, sweep.at)

    moved = {d.account_id: _sign(D(d.unexplained)) for d in sweep.detections}
    for detection in sweep.detections:
        direction = moved[detection.account_id]
        peers = sweep.observed - {detection.account_id}
        detection.peers_observed = len(peers)
        detection.peers_moved = sum(
            1 for account_id in peers if moved.get(account_id) == direction
        )
        detection.traded_in_window = detection.account_id in traded
        verdict = classify(
            detection,
            peers_observed=detection.peers_observed,
            peers_moved=detection.peers_moved,
            traded=detection.traded_in_window,
        )
        detection.suggested_class = verdict.kind
        detection.classification_reason = verdict.reason
        detection.confident = verdict.confident
        if verdict.kind == MovementClass.INVESTOR:
            detection.suggested_kind = (
                "deposit" if D(detection.unexplained) > ZERO else "withdrawal"
            )
        detection.save(
            update_fields=[
                "suggested_class",
                "suggested_kind",
                "classification_reason",
                "confident",
                "peers_observed",
                "peers_moved",
                "traded_in_window",
            ]
        )
        _auto_resolve(detection)
    return sweep.detections


def _auto_resolve(detection: DetectedMovement) -> None:
    """Apply the verdict, if the configured mode allows it.

    ``off`` decides nothing and leaves the whole queue to a person. ``safe``
    acts on the confident rules only. ``all`` acts on everything, including the
    standing default — which books nothing, so the cost of being wrong is a
    PnL that carries a transfer until somebody reopens the row.
    """
    from apps.accounts import bookkeeping

    mode = str(settings.LEDGER["AUTO_RESOLVE"]).lower()
    if mode == "off" or (mode != "all" and not detection.confident):
        return
    if detection.status != DetectionStatus.PENDING:
        return

    note = f"auto: {detection.classification_reason}"
    if detection.suggested_class == MovementClass.INVESTOR:
        bookkeeping.accept_detection(detection, actor="", note=note, auto=True)
    else:
        bookkeeping.attribute_detection(detection, actor="", note=note, auto=True)
