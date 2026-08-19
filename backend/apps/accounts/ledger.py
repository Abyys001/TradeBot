"""The financial ledger: deposits, withdrawals, balance, PnL and the profit split.

Two data sources, combined here and nowhere else:

- **Cash flows** — ``FundMovement`` rows, recorded by hand. The platform's keys
  are trade-only (spec §7), so no exchange API can tell us who moved money in or
  out; manual entry is the only honest source, and it starts "from now on".
- **Current balance** — ``ConnectedAccount.last_balance``, the exchange's live
  number from the regular polling.

Every number is ``Decimal`` and every comparison is on ``Decimal``; money never
touches float (``apps/core/money.py``).

Reading rules that the view enforces by passing a pre-narrowed queryset:

- **Non-USDT** accounts are listed with their own numbers but excluded from the
  USDT totals and flagged, exactly as the dashboard treats them (Q4).
- A balance that has never been fetched is ``None`` on the row, and that account
  is left out of the aggregated sums — the totals never turn an unknown balance
  into a zero (there is no synthetic data anywhere in this codebase).

The split (profit-only): an account's profit is split by the three global
percentages from ``ProfitSplit``. On a loss there is nothing to divide, so the
share amounts are 0 and the loss is shown as the PnL number.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from apps.accounts.models import FundMovementType
from apps.core.money import ZERO, D

if TYPE_CHECKING:  # pragma: no cover - typing only
    from django.db.models import QuerySet

    from apps.accounts.models import ConnectedAccount

ROLES = ("investor", "trader", "programmer")

#: The seed row, created on first read. Edited from the panel's Settings.
DEFAULT_SPLIT = {"investor": "60", "trader": "20", "programmer": "20"}


def get_split():
    """The one ``ProfitSplit`` row, created with the default split if absent."""
    from apps.accounts.models import ProfitSplit

    row, _ = ProfitSplit.objects.get_or_create(
        singleton=1, defaults={**DEFAULT_SPLIT, "singleton": 1}
    )
    return row


def split_pcts() -> dict[str, Decimal]:
    row = get_split()
    return {role: D(getattr(row, role)) for role in ROLES}


def _net_movements(account) -> tuple[Decimal, Decimal, Decimal]:
    """(deposits, withdrawals, net) for one account, all Decimal.

    Iterates the related manager so a ``prefetch_related("fund_movements")``
    queryset is served from the cache — one query for the whole snapshot.
    """
    deposits = ZERO
    withdrawals = ZERO
    for movement in account.fund_movements.all():
        amount = D(movement.amount)
        if movement.kind == FundMovementType.DEPOSIT:
            deposits += amount
        else:
            withdrawals += amount
    return deposits, withdrawals, deposits - withdrawals


def _pct(pnl: Decimal | None, net: Decimal) -> Decimal | None:
    """PnL as a percentage of net invested; None when it cannot be argued."""
    if pnl is None or net is None or net <= ZERO:
        return None
    return pnl / net * Decimal("100")


def _shares(pnl: Decimal | None) -> dict[str, Decimal]:
    """Per-role share of a *positive* PnL. Loss means nothing to divide."""
    zero = {role: ZERO for role in ROLES}
    if pnl is None or pnl <= ZERO:
        return zero
    pcts = split_pcts()
    return {role: pnl * pcts[role] / Decimal("100") for role in ROLES}


def account_ledger(account: ConnectedAccount) -> dict[str, Any]:
    """One account's row: what went in, what came out, what it is worth now.

    ``current_balance`` is None until the exchange has answered at least once;
    ``pnl`` and ``pnl_pct`` are then None too — unknown, not zero.
    """
    deposits, withdrawals, net = _net_movements(account)
    # ``D`` absorbs a still-string in-memory attribute; from the DB it is already
    # Decimal, so this is purely defensive. None stays None. Quantised to the
    # movement precision so the row prints one consistent shape.
    current = None if account.last_balance is None else D(account.last_balance)
    if current is not None:
        current = current.quantize(Decimal("0.00000001"))
    pnl = current - net if current is not None else None
    pnl_pct = _pct(pnl, net)
    shares = _shares(pnl)
    return {
        "account": account.id,
        "label": account.label,
        "exchange": account.exchange,
        "exchange_label": account.get_exchange_display(),
        "status": account.status,
        "testnet": account.testnet,
        "hidden": account.hidden,
        "asset": account.last_balance_asset or "USDT",
        "balance_is_usdt": account.balance_is_usdt,
        "deposits": str(deposits),
        "withdrawals": str(withdrawals),
        "net_invested": str(net),
        "current_balance": str(current) if current is not None else None,
        "pnl": str(pnl) if pnl is not None else None,
        "pnl_pct": str(pnl_pct) if pnl_pct is not None else None,
        "shares": {role: str(amount) for role, amount in shares.items()},
    }


def _sum(rows: list[dict], key: str) -> Decimal:
    return sum((D(row[key]) for row in rows if row[key] is not None), ZERO)


def _priced(rows: list[dict]) -> list[dict]:
    """Rows with a known USDT balance — the ones that can join the totals.

    An account that has never been priced has a real ``net_invested`` but no
    ``current_balance``; folding its capital into the aggregate would corrupt
    the PnL, so it stays out and is listed individually.
    """
    return [
        row for row in rows if row["current_balance"] is not None and row["balance_is_usdt"]
    ]


def aggregate(rows: list[dict]) -> dict[str, Any]:
    """Sum a set of account rows into a group (exchange or grand total)."""
    priced = _priced(rows)
    net = _sum(priced, "net_invested")
    current = _sum(priced, "current_balance")
    pnl = _sum(priced, "pnl")
    shares = {
        role: sum((D(row["shares"][role]) for row in priced), ZERO) for role in ROLES
    }
    return {
        "accounts": len(priced),
        "net_invested": str(net),
        "current_balance": str(current),
        "pnl": str(pnl),
        "pnl_pct": str(_pct(pnl, net)) if _pct(pnl, net) is not None else None,
        "shares": {role: str(amount) for role, amount in shares.items()},
    }


def ledger_snapshot(accounts: QuerySet[ConnectedAccount]) -> dict[str, Any]:
    """The full financial-management payload.

    ``accounts`` must already be narrowed to what the caller may see — totals
    are recomputed over those rows only, never copied from a wider set.
    """
    rows = [account_ledger(a) for a in accounts.prefetch_related("fund_movements")]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["exchange"], []).append(row)

    exchanges = [
        {
            "exchange": key,
            "label": group[0]["exchange_label"],
            **aggregate(group),
        }
        for key, group in sorted(grouped.items())
    ]
    return {
        "accounts": rows,
        "exchanges": exchanges,
        "totals": aggregate(rows),
        "split": {role: str(pct) for role, pct in split_pcts().items()},
        "non_usdt": [
            {"account": row["account"], "label": row["label"], "asset": row["asset"]}
            for row in rows
            if not row["balance_is_usdt"]
        ],
    }
