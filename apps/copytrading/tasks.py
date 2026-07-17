"""Copy-signal fan-out: mirror a master strategy's entries/closes to investors.

The master's live runner calls :func:`record_and_fanout` after each bar. It
persists a ``CopySignal`` and (via Celery) fans it out to every active
subscription, sizing from the investor's own balance and routing through their
own exchange client. Everything is best-effort per investor so one failing
account never blocks the rest.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction

from apps.exchange.base import get_client

from .models import CopySignal, FeeConfig, FeeLedger, InvestorPosition, Subscription
from .sizing import accrue_fee, compute_size, realized_pnl

logger = logging.getLogger(__name__)


def record_and_fanout(
    master_strategy, *, action: str, direction: str, coin: str, price: float, ts: int
) -> CopySignal | None:
    """Persist a copy signal for a published master and queue fan-out.

    No-op (returns None) when the strategy is not a published master, so the
    live runner can call this unconditionally.
    """
    if not (master_strategy.is_master and master_strategy.published):
        return None
    signal = CopySignal.objects.create(
        master_strategy=master_strategy,
        action=action,
        direction=direction or "",
        coin=coin,
        price=Decimal(str(price)),
        ts=int(ts),
    )
    fanout_copy_signal_task.delay(signal.pk)
    return signal


@shared_task
def fanout_copy_signal_task(signal_id: int) -> dict:
    signal = CopySignal.objects.select_related("master_strategy").get(pk=signal_id)
    return fanout_signal(signal)


def fanout_signal(signal: CopySignal) -> dict:
    """Synchronous fan-out core (called by the task; unit-testable)."""
    subs = Subscription.objects.filter(
        master_strategy=signal.master_strategy, is_active=True
    ).select_related("credential", "investor")
    results = {"signal": signal.pk, "mirrored": 0, "skipped": 0, "errors": []}
    for sub in subs:
        try:
            if not _investor_may_trade(sub):
                results["skipped"] += 1
                continue
            if signal.action == CopySignal.Action.ENTRY:
                _mirror_entry(sub, signal)
            else:
                _mirror_close(sub, signal)
            results["mirrored"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fanout failed sub %s signal %s: %s", sub.pk, signal.pk, type(exc).__name__
            )
            results["errors"].append({"subscription": sub.pk, "error": str(exc)})
    return results


def _investor_may_trade(sub: Subscription) -> bool:
    """Honour the investor's master kill-switch and active credential."""
    return bool(sub.investor.is_trading_enabled and sub.credential.is_active)


def _mirror_entry(sub: Subscription, signal: CopySignal) -> None:
    client = get_client(sub.credential)
    is_long = signal.direction == CopySignal.Direction.LONG
    price = float(signal.price)
    balance = client.balance() if sub.sizing_mode == Subscription.Sizing.RISK_PCT else 0.0
    size = compute_size(
        balance=balance,
        price=price,
        sizing_mode=sub.sizing_mode,
        risk_pct=sub.risk_pct,
        fixed_notional=sub.fixed_notional,
        leverage=sub.leverage,
    )
    if size <= 0:
        raise ValueError("computed size is zero (check balance / notional)")

    if sub.leverage > 1:
        client.set_leverage(signal.coin, sub.leverage)
    resp = client.place_order(signal.coin, is_buy=is_long, size=size, price=None)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "order rejected"))

    signed = size if is_long else -size
    InvestorPosition.objects.update_or_create(
        subscription=sub,
        coin=signal.coin,
        defaults={"size": Decimal(str(signed)), "entry_price": signal.price},
    )


def _mirror_close(sub: Subscription, signal: CopySignal) -> None:
    try:
        pos = InvestorPosition.objects.get(subscription=sub, coin=signal.coin)
    except InvestorPosition.DoesNotExist:
        return  # nothing open to close for this investor

    client = get_client(sub.credential)
    resp = client.close_position(signal.coin)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "close rejected"))

    delta = realized_pnl(
        entry_price=float(pos.entry_price),
        exit_price=float(signal.price),
        size=float(pos.size),
    )
    _apply_fee(sub, delta)
    pos.delete()


def _apply_fee(sub: Subscription, realized_delta: float) -> float:
    """Update the subscription's fee ledger under a high-water mark."""
    with transaction.atomic():
        ledger, created = FeeLedger.objects.select_for_update().get_or_create(
            subscription=sub,
            defaults={"fee_rate": FeeConfig.get_solo().fee_rate},
        )
        fee, new_realized, new_hwm = accrue_fee(
            prior_realized=ledger.realized_pnl,
            prior_hwm=ledger.high_water_mark,
            realized_delta=realized_delta,
            fee_rate=ledger.fee_rate,
        )
        ledger.realized_pnl = Decimal(str(new_realized))
        ledger.high_water_mark = Decimal(str(new_hwm))
        ledger.fee_accrued = ledger.fee_accrued + Decimal(str(fee))
        ledger.save(
            update_fields=["realized_pnl", "high_water_mark", "fee_accrued", "updated_at"]
        )
    return fee
