"""Performance-fee accrual with a per-subscription high-water mark.

On each closed CopyTrade we recompute the subscription's cumulative realized
profit. A fee (default 20%) is charged only on the portion that lifts cumulative
profit above its previous high-water mark, so an investor is never charged twice
for recovering the same drawdown. Fees are accrued to a ledger (FeeLedgerEntry);
collection is off-platform (trade-only keys can't move funds on-chain).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
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

    Uses select_for_update + atomic F() update to prevent double-fee accrual
    under concurrent close events.
    """
    sub = copy_trade.subscription

    with transaction.atomic():
        # Lock the subscription row to prevent concurrent HWM reads.
        sub_locked = type(sub).objects.select_for_update().get(pk=sub.pk)

        agg = CopyTrade.objects.filter(
            subscription=sub_locked, status=CopyTrade.Status.CLOSED
        ).aggregate(total=Sum("gross_pnl"))
        cumulative = Decimal(agg["total"] or 0)
        hwm = Decimal(sub_locked.high_water_mark or 0)

        if cumulative <= hwm:
            return None  # still under water vs the previous peak — no fee

        profit_above = cumulative - hwm
        pct = _share_pct(sub_locked)
        fee = (profit_above * pct / Decimal(100)).quantize(_CENT)

        # Atomic HWM update — no race window.
        type(sub_locked).objects.filter(pk=sub_locked.pk).update(high_water_mark=cumulative)

    if fee <= 0:
        return None

    entry = FeeLedgerEntry.objects.create(
        subscription=sub_locked, trade=copy_trade, amount=fee, share_pct=pct
    )
    copy_trade.platform_share_amount = fee
    copy_trade.save(update_fields=["platform_share_amount"])
    return entry
