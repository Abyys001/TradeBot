"""Copy-trading Celery tasks: signal fan-out and equity snapshots."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="copytrading.fan_out_signal")
def fan_out_signal_task(strategy_id: int, actions: list[dict]):
    """Replay captured signal intents against every active subscriber's account.

    Per-account isolation: one investor's failure must never block the others.
    """
    from apps.strategies.models import Strategy
    from apps.transpiler.runtime.tabdeal_broker import TabdealBroker

    from .models import CopySubscription

    strategy = Strategy.objects.select_related("user").get(pk=strategy_id)
    signal = getattr(strategy, "copy_signal", None)
    if signal is None or not signal.is_active:
        return {"ok": False, "reason": "no active signal"}

    live_config = strategy.live_config or {}
    leverage = float(live_config.get("leverage", 1) or 1)

    subs = CopySubscription.objects.filter(signal=signal, is_active=True).select_related(
        "credential", "credential__user", "signal"
    )
    done = 0
    for sub in subs:
        try:
            broker = TabdealBroker(sub, strategy, strategy.symbol, leverage=leverage)
            for a in actions:
                _apply_action(broker, a)
            done += 1
        except Exception:  # noqa: BLE001 — isolate per-investor failures
            logger.exception("fan-out failed for subscription %s", sub.pk)
    return {"ok": True, "subscribers": done, "actions": len(actions)}


def _apply_action(broker, a: dict) -> None:
    t = a.get("type")
    if t == "entry":
        broker.entry(
            a["oid"], a["direction"], a["price"], a["bar_index"],
            qty=a.get("qty"), limit=a.get("limit"), alert_message=a.get("alert_message"),
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
