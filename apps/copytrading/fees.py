"""Performance-fee accrual with a per-subscription high-water mark.

On each closed CopyTrade we recompute the subscription's cumulative realized
profit. A fee (default 20%) is charged only on the portion that lifts cumulative
profit above its previous high-water mark, so an investor is never charged twice
for recovering the same drawdown. Fees are accrued to a ledger (FeeLedgerEntry);
collection is off-platform (trade-only keys can't move funds on-chain).
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import CopyTrade, FeeLedgerEntry, PlatformFeeConfig

_CENT = Decimal("0.00000001")


def _share_pct(subscription) -> Decimal:
    signal = subscription.signal
    cfg = PlatformFeeConfig.objects.filter(owner=signal.owner).first()
    if cfg is not None:
        return Decimal(cfg.share_pct)
    return Decimal(signal.platform_share_pct)


def apply_profit_share(copy_trade) -> "FeeLedgerEntry | None":
    """Accrue the platform's share for a just-closed trade, honouring the HWM.

    Returns the created FeeLedgerEntry, or None if no new high was reached.
    """
    sub = copy_trade.subscription

    agg = CopyTrade.objects.filter(subscription=sub, status=CopyTrade.Status.CLOSED).aggregate(
        total=Sum("gross_pnl")
    )
    cumulative = Decimal(agg["total"] or 0)
    hwm = Decimal(sub.high_water_mark or 0)

    if cumulative <= hwm:
        return None  # still under water vs the previous peak — no fee

    profit_above = cumulative - hwm
    pct = _share_pct(sub)
    fee = (profit_above * pct / Decimal(100)).quantize(_CENT)

    sub.high_water_mark = cumulative
    sub.save(update_fields=["high_water_mark"])

    if fee <= 0:
        return None

    entry = FeeLedgerEntry.objects.create(
        subscription=sub, trade=copy_trade, amount=fee, share_pct=pct
    )
    copy_trade.platform_share_amount = fee
    copy_trade.save(update_fields=["platform_share_amount"])
    return entry
