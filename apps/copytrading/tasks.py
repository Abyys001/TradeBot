"""Copy-trading Celery tasks: signal fan-out, equity snapshots, and reconciliation.

Supports both Hyperliquid (record_and_fanout) and Tabdeal (fan_out_signal_task)
signal fan-out paths.
"""
from __future__ import annotations

import hashlib
import logging
import time
from decimal import Decimal

from celery import shared_task
from django.db import transaction

from apps.exchange.base import get_client

from .models import CopySignal, FeeConfig, FeeLedger, InvestorPosition, Subscription

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


@shared_task(name="copytrading.fan_out_signal")
def fan_out_signal_task(strategy_id: int, actions: list[dict]):
    """Replay captured signal intents against every active subscriber's account.

    Per-account isolation: one investor's failure must never block the others.
    Orders use unique clientOrderId for idempotency (error 1213 = already placed).
    Pre-trade risk checks gate each investor independently.
    """
    from apps.exchange.tabdeal_errors import TabdealAPIError
    from apps.exchange.tabdeal_futures import TabdealFuturesClient
    from apps.risk.config import parse_risk_config
    from apps.risk.manager import RiskManager
    from apps.strategies.models import Strategy
    from apps.transpiler.runtime.tabdeal_broker import TabdealBroker

    from .models import CopySubscription

    strategy = Strategy.objects.select_related("user").get(pk=strategy_id)
    signal = getattr(strategy, "copy_signal", None)
    if signal is None or not signal.is_active:
        return {"ok": False, "reason": "no active signal"}

    live_config = strategy.live_config or {}
    leverage = float(live_config.get("leverage", 1) or 1)
    risk_config = parse_risk_config(live_config)

    subs = CopySubscription.objects.filter(signal=signal, is_active=True).select_related(
        "credential", "credential__user", "signal"
    )
    done = 0
    errors = []
    skipped_risk = []
    for sub in subs:
        try:
            # Pre-trade risk gate per investor.
            try:
                client = TabdealFuturesClient(sub.credential)
                equity = client.available_usdt()
            except Exception:  # noqa: BLE001
                equity = 0.0

            rm = RiskManager(config=risk_config, initial_balance=equity, strategy_id=sub.pk)
            risk_decision = rm.pre_trade(
                equity=equity,
                open_trades=0,
                exposure_pct=0.0,
                leverage=leverage,
            )
            if not risk_decision.ok:
                skipped_risk.append({"subscription_id": sub.pk, "reason": risk_decision.reason})
                continue

            broker = TabdealBroker(sub, strategy, strategy.symbol, leverage=leverage)
            for a in actions:
                _apply_action(broker, a, sub)
            done += 1
        except TabdealAPIError as exc:
            code = exc.info.code
            if code == "1213":
                logger.info("duplicate order for sub %s (idempotent)", sub.pk)
            else:
                logger.warning("tabdeal error for sub %s: %s", sub.pk, exc)
                errors.append({"subscription_id": sub.pk, "code": code, "message": exc.info.message})
        except Exception:  # noqa: BLE001 — isolate per-investor failures
            logger.exception("fan-out failed for subscription %s", sub.pk)
            errors.append({"subscription_id": sub.pk, "error": "internal"})
    return {"ok": True, "subscribers": done, "actions": len(actions), "errors": errors, "skipped_risk": skipped_risk}


def _generate_client_order_id(sub_id: int, action: dict, timestamp: float) -> str:
    """Generate a deterministic, unique clientOrderId for idempotency."""
    raw = f"cp:{sub_id}:{action.get('type', '')}:{action.get('oid', '')}:{int(timestamp * 1000)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _apply_action(broker, a: dict, sub=None) -> None:
    t = a.get("type")
    ts = time.time()
    coid = _generate_client_order_id(sub.pk if sub else 0, a, ts) if sub else None
    if t == "entry":
        broker.entry(
            a["oid"], a["direction"], a["price"], a["bar_index"],
            qty=a.get("qty"), limit=a.get("limit"), alert_message=a.get("alert_message"),
            client_order_id=coid,
        )
    elif t == "close":
        broker.close(a["oid"], a["price"], a["bar_index"], qty_pct=a.get("qty_pct", 1.0), reason=a.get("reason"))
    elif t == "exit":
        broker.exit(a["oid"], a["price"], a["bar_index"], stop=a.get("stop"), limit=a.get("limit"), update=a.get("update"))


@shared_task(name="copytrading.capture_equity")
def capture_equity_task(subscription_id: int | None = None):
    """Snapshot investor equity for equity-curve charts. All active subs if id omitted."""
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    from .models import CopySubscription, EquitySnapshot

    qs = CopySubscription.objects.filter(is_active=True).select_related("credential")
    if subscription_id is not None:
        qs = qs.filter(pk=subscription_id)

    n = 0
    for sub in qs:
        try:
            client = TabdealFuturesClient(sub.credential)
            balances = client.get_balance()
            wallet = 0.0
            unrealized = 0.0
            for b in balances:
                if b.get("asset") == "USDT":
                    wallet = float(b.get("walletBalance", 0) or 0)
                    unrealized = float(b.get("crossUnPnl", 0) or 0)
                    break
            EquitySnapshot.objects.create(
                subscription=sub, balance=str(wallet), equity=str(wallet + unrealized)
            )
            n += 1
        except Exception:  # noqa: BLE001
            logger.warning("equity snapshot failed for sub %s", sub.pk, exc_info=True)
    return {"ok": True, "snapshots": n}


@shared_task(name="copytrading.reconcile_copy_orders")
def reconcile_copy_orders_task():
    """Poll Tabdeal for open positions and recent trades to reconcile CopyOrder/CopyTrade status.

    Runs periodically to detect: orphaned positions, missed fills, stale order states.
    """
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    from .models import CopyOrder, CopySubscription, CopyTrade

    active_subs = CopySubscription.objects.filter(
        is_active=True,
        credential__is_active=True,
    ).select_related("credential", "credential__user")

    reconciled = 0
    errors = 0
    for sub in active_subs:
        try:
            client = TabdealFuturesClient(sub.credential)

            # Reconcile open copy orders against exchange state.
            open_orders = CopyOrder.objects.filter(
                subscription=sub,
                status__in=["pending", "submitted", "partially_filled"],
            )
            exchange_open = {o.get("orderId"): o for o in client.open_orders(sub.signal.strategy.symbol if sub.signal and sub.signal.strategy else None)}

            for order in open_orders:
                ex = exchange_open.get(int(order.exchange_order_id)) if order.exchange_order_id else None
                if ex is None:
                    # Order no longer on exchange — check if filled or canceled.
                    order.status = "filled" if float(order.filled_size or 0) >= float(order.size) else "canceled"
                    order.save(update_fields=["status", "updated_at"])
                elif ex.get("status") == "FILLED":
                    order.status = "filled"
                    order.filled_size = ex.get("executedQty", order.filled_size)
                    order.save(update_fields=["status", "filled_size", "updated_at"])
                reconciled += 1

            # Detect orphaned positions (open on exchange but no matching CopyTrade).
            positions = client.get_positions()
            for p in positions:
                amt = float(p.get("positionAmt", 0))
                if amt == 0:
                    continue
                has_trade = CopyTrade.objects.filter(
                    subscription=sub,
                    status=CopyTrade.Status.OPEN,
                    entry_order__pair=p.get("symbol", ""),
                ).exists()
                if not has_trade:
                    logger.warning(
                        "orphaned position detected for sub %s: %s amt=%s",
                        sub.pk, p.get("symbol"), amt,
                    )

        except Exception:  # noqa: BLE001
            logger.warning("reconciliation failed for sub %s", sub.pk, exc_info=True)
            errors += 1

    return {"ok": True, "reconciled": reconciled, "errors": errors}
