"""One account, whole: the payload behind the per-account page.

The accounts list answers "is it connected and what is it worth". This answers
the next question — *what has this connection actually done since it was
plugged in*: when it joined, what was paid in and taken out, every leg it was
given and what each one returned, and what the platform has on record about
changing any of it.

Nothing here is a new source of truth. The money figures come from
``apps.accounts.ledger`` so this page and the finance page can never disagree
about one account; the trade figures are the account's own ``TradeLeg`` rows,
which is what spec §8 calls per-account history. Every number is ``Decimal``
and leaves as a string, exactly as the ledger does.

Unknown stays unknown: a leg the exchange never priced has ``pnl`` null and is
counted in neither the wins nor the losses, and an account the exchange has
never answered for has a null balance rather than a zero.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q

from apps.accounts.ledger import account_ledger, split_pcts
from apps.accounts.models import (
    ConnectedAccount,
    DetectedMovement,
    FundMovement,
    Notification,
)
from apps.accounts.serializers import (
    ConnectedAccountSerializer,
    DetectedMovementSerializer,
    FundMovementSerializer,
    NotificationSerializer,
)
from apps.core.money import ZERO, D
from apps.trading.models import TradeLeg

#: These tables only grow, and the page wants the account's history, not a
#: paginator. Capped for the same reason the audit trail and the system log are.
LEG_LIMIT = 500
NOTICE_LIMIT = 200

#: The money audit trail is *not* here. ``/accounts/ledger/events/?account=``
#: already serves it and the panel already has a component for it, and two
#: copies of an audit trail is one too many places for it to be wrong.


def _str(value) -> str | None:
    return None if value is None else str(D(value))


def _leg_row(leg: TradeLeg) -> dict[str, Any]:
    """One leg with the trade it belonged to folded in.

    The trade fields ride along rather than being fetched per row by the panel:
    a leg's PnL is unreadable without the pair, the side and the leverage that
    produced it.
    """
    trade = leg.trade
    qty = D(leg.qty) if leg.qty is not None else None
    entry = D(leg.entry_price) if leg.entry_price is not None else None
    notional = qty * entry if qty is not None and entry is not None else None
    pnl = D(leg.pnl) if leg.pnl is not None else None
    margin = D(leg.margin) if leg.margin is not None else None
    return {
        "id": leg.id,
        "trade": trade.id,
        "symbol": trade.symbol,
        "side": trade.side,
        "market": trade.market,
        "order_type": trade.order_type,
        "leverage": trade.leverage,
        "sl_pct": _str(trade.sl_pct),
        "tp_pct": _str(trade.tp_pct),
        "sltp_basis": trade.sltp_basis,
        "trade_status": trade.status,
        "fanout_ms": trade.fanout_ms,
        "ok": leg.ok,
        "error": leg.error,
        "error_code": leg.error_code,
        "dispatch_ms": leg.dispatch_ms,
        "qty": _str(leg.qty),
        "entry_price": _str(leg.entry_price),
        "exit_price": _str(leg.exit_price),
        "margin": _str(leg.margin),
        "notional": _str(notional),
        "stop_loss": _str(leg.stop_loss),
        "take_profit": _str(leg.take_profit),
        "sltp_attached": leg.sltp_attached,
        "sltp_verified": leg.sltp_verified,
        "pnl": _str(leg.pnl),
        # Return on the margin this leg actually locked up — the only honest
        # denominator for a leveraged position, and the figure the account's
        # own exchange screen shows.
        "roe_pct": (
            str(pnl / margin * Decimal("100"))
            if pnl is not None and margin is not None and margin > ZERO
            else None
        ),
        "opened_at": leg.opened_at,
        "closed_at": leg.closed_at,
        "open": leg.ok and leg.closed_at is None,
    }


def trading_summary(rows: list[dict]) -> dict[str, Any]:
    """What this account's legs add up to. Unpriced legs are counted nowhere."""
    scored = [row for row in rows if row["pnl"] is not None]
    wins = [row for row in scored if D(row["pnl"]) > ZERO]
    losses = [row for row in scored if D(row["pnl"]) < ZERO]
    realised = sum((D(row["pnl"]) for row in scored), ZERO)
    gross_profit = sum((D(row["pnl"]) for row in wins), ZERO)
    gross_loss = sum((D(row["pnl"]) for row in losses), ZERO)
    volume = sum(
        (D(row["notional"]) for row in rows if row["notional"] is not None), ZERO
    )
    times = [row["opened_at"] for row in rows if row["opened_at"] is not None]
    return {
        "legs": len(rows),
        "filled": len([row for row in rows if row["ok"]]),
        "failed": len([row for row in rows if not row["ok"]]),
        "open": len([row for row in rows if row["open"]]),
        "scored": len(scored),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": str(D(len(wins)) / D(len(scored)) * Decimal("100")) if scored else None,
        "realised_pnl": str(realised),
        "gross_profit": str(gross_profit),
        "gross_loss": str(gross_loss),
        # Gross profit over gross loss. Null rather than infinity when nothing
        # has lost yet — a ratio with no denominator is not a good result, it
        # is an absent one.
        "profit_factor": (
            str(gross_profit / abs(gross_loss)) if gross_loss < ZERO else None
        ),
        "average_pnl": str(realised / D(len(scored))) if scored else None,
        "best": str(max(D(row["pnl"]) for row in scored)) if scored else None,
        "worst": str(min(D(row["pnl"]) for row in scored)) if scored else None,
        "volume": str(volume),
        "first_trade_at": min(times) if times else None,
        "last_trade_at": max(times) if times else None,
    }


def pnl_curve(rows: list[dict]) -> list[dict[str, Any]]:
    """Realised PnL as it accumulated, oldest first — the page's one line chart.

    Only priced legs are points: a leg the venue never priced would otherwise
    draw a flat step that reads as a break-even trade.
    """
    scored = [row for row in rows if row["pnl"] is not None]
    scored.sort(key=lambda row: (row["closed_at"] or row["opened_at"], row["id"]))
    running = ZERO
    points = []
    for row in scored:
        running += D(row["pnl"])
        points.append(
            {
                "at": row["closed_at"] or row["opened_at"],
                "symbol": row["symbol"],
                "pnl": row["pnl"],
                "cumulative": str(running),
            }
        )
    return points


def by_symbol(rows: list[dict]) -> list[dict[str, Any]]:
    """Per-pair totals, worst-to-best by PnL — where the money was made or lost."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row["symbol"], {"symbol": row["symbol"], "legs": 0, "wins": 0, "pnl": ZERO}
        )
        bucket["legs"] += 1
        if row["pnl"] is not None:
            value = D(row["pnl"])
            bucket["pnl"] += value
            if value > ZERO:
                bucket["wins"] += 1
    return sorted(
        ({**bucket, "pnl": str(bucket["pnl"])} for bucket in grouped.values()),
        key=lambda bucket: D(bucket["pnl"]),
        reverse=True,
    )


def account_report(account: ConnectedAccount) -> dict[str, Any]:
    """The whole page in one request.

    One round trip rather than six: every block here is about the same account,
    and a page that renders its balance before its trades and its trades before
    its cash flows is a page that is wrong three times on the way to being
    right.
    """
    legs = (
        TradeLeg.objects.filter(account=account)
        .select_related("trade")
        .order_by("-opened_at", "-id")[:LEG_LIMIT]
    )
    rows = [_leg_row(leg) for leg in legs]

    movements = FundMovement.objects.filter(account=account).select_related("account")
    detections = DetectedMovement.objects.filter(account=account).select_related("account")
    notifications = Notification.objects.filter(account=account)[:NOTICE_LIMIT]

    return {
        "account": ConnectedAccountSerializer(account).data,
        # Spec §6's "since when": connected at, and eligible from — the same
        # date until the account is paused and resumed, and deliberately both
        # after that, because a resume restarts the eligibility clock while the
        # connection itself is older.
        "connected_at": account.created_at,
        "eligible_from": account.eligible_from,
        "ledger": account_ledger(account),
        "split": {role: str(value) for role, value in split_pcts().items()},
        "trading": trading_summary(rows),
        "legs": rows,
        "curve": pnl_curve(rows),
        "symbols": by_symbol(rows),
        "movements": FundMovementSerializer(movements, many=True).data,
        "detections": DetectedMovementSerializer(detections, many=True).data,
        "notifications": NotificationSerializer(notifications, many=True).data,
        "leg_limit": LEG_LIMIT,
    }


# --- the statement window -------------------------------------------------
#
# The page above answers "everything, ever". A statement answers "this account,
# between these two dates", which is a different question and has one trap in
# it: a lifetime figure printed under a period heading is a lie. So the window
# narrows the *events* — legs and cash flows — and every whole-life figure
# (balance, net invested, PnL since inception) is carried through unchanged and
# labelled as what it is.
#
# A leg belongs to the window it was **realised** in, not the one it was opened
# in: that is when the money moved. A leg that was live during the window but
# had not closed by ``end`` is listed as open and contributes nothing to the
# period's result, and a leg that never got sent is listed as the failure it
# was.


def _in_window(value, start, end) -> bool:
    if value is None:
        return False
    if start is not None and value < start:
        return False
    return not (end is not None and value >= end)


def statement_report(account: ConnectedAccount, start=None, end=None) -> dict[str, Any]:
    """One account between two instants — the payload the PDF receipt prints.

    ``start``/``end`` are timezone-aware and half-open (``start <= t < end``);
    either may be None for an open-ended side, and both None is the account's
    whole life.
    """
    legs = TradeLeg.objects.filter(account=account).select_related("trade")
    # Anything that was live at some point inside the window: opened before it
    # ended, and either closed inside it or still running when it ended.
    if end is not None:
        legs = legs.filter(opened_at__lt=end)
    if start is not None:
        legs = legs.filter(
            Q(opened_at__gte=start) | Q(closed_at__isnull=True) | Q(closed_at__gte=start)
        )
    rows = [_leg_row(leg) for leg in legs.order_by("opened_at", "id")]

    # Three disjoint sets, because they answer three different questions and
    # summing them together would answer none of them.
    closed = [row for row in rows if row["ok"] and _in_window(row["closed_at"], start, end)]
    realised_ids = {row["id"] for row in closed}
    still_open = [row for row in rows if row["ok"] and row["id"] not in realised_ids]
    failed = [row for row in rows if not row["ok"]]

    movements = list(
        FundMovement.objects.filter(account=account)
        .filter(**{k: v for k, v in (("occurred_at__gte", start), ("occurred_at__lt", end)) if v})
        .order_by("occurred_at", "id")
    )
    deposits = sum((D(m.amount) for m in movements if m.kind == "deposit"), ZERO)
    withdrawals = sum((D(m.amount) for m in movements if m.kind != "deposit"), ZERO)

    return {
        "account": ConnectedAccountSerializer(account).data,
        "connected_at": account.created_at,
        "eligible_from": account.eligible_from,
        "period": {"start": start, "end": end},
        # Whole-life, deliberately: what the account is worth and what it has
        # returned since inception cannot be windowed, and the receipt says so.
        "ledger": account_ledger(account),
        "split": {role: str(value) for role, value in split_pcts().items()},
        # Period result: realised legs only. An open position has not returned
        # anything yet and an unsent order returned nothing at all.
        "trading": trading_summary(closed),
        "closed": closed,
        "open": still_open,
        "failed": failed,
        "symbols": by_symbol(closed),
        "movements": FundMovementSerializer(movements, many=True).data,
        "flows": {
            "deposits": str(deposits),
            "withdrawals": str(withdrawals),
            "net": str(deposits - withdrawals),
            "count": len(movements),
        },
    }
