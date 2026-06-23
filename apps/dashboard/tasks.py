"""Dashboard Celery tasks: emergency stop and health heartbeat."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="dashboard.emergency_stop_all")
def emergency_stop_all_task(user_id: int) -> dict:
    """Stop all active strategies and optionally close exchange positions."""
    from apps.accounts.models import User
    from apps.credentials.models import ExchangeCredential
    from apps.exchange.hl_client import cancel_all_orders, close_all_positions
    from apps.execution.models import ExecutionLog
    from apps.strategies.models import Strategy
    from apps.transpiler.tasks import stop_live_strategy_task

    user = User.objects.get(pk=user_id)
    user.is_trading_enabled = False
    user.save(update_fields=["is_trading_enabled"])

    stopped = []
    for strategy in Strategy.objects.filter(user=user, status=Strategy.Status.ACTIVE):
        stop_live_strategy_task.delay(strategy.pk)
        strategy.status = Strategy.Status.STOPPED
        strategy.save(update_fields=["status"])
        stopped.append(strategy.pk)

    cancelled = []
    cred_ids = (
        ExchangeCredential.objects.filter(user=user, is_active=True)
        .values_list("pk", flat=True)
        .distinct()
    )
    for cred in ExchangeCredential.objects.filter(pk__in=cred_ids):
        try:
            cancel_result = cancel_all_orders(cred)
            close_result = close_all_positions(cred)
            cancelled.append({
                "credential_id": cred.pk,
                "cancel": cancel_result.get("ok", False),
                "close": close_result.get("ok", False),
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("emergency stop failed for cred %s", cred.pk)
            cancelled.append({"credential_id": cred.pk, "ok": False, "error": str(exc)})

    ExecutionLog.objects.create(
        strategy=None,
        level=ExecutionLog.Level.WARNING,
        event="kill_switch.triggered",
        payload={"user_id": user_id, "stopped_strategies": stopped, "cancelled": cancelled},
    )

    from apps.dashboard.publish import publish_dashboard

    publish_dashboard(
        user_id,
        {
            "source": "kill_switch",
            "enabled": False,
            "stopped_strategies": stopped,
            "cancelled": cancelled,
        },
    )
    return {"ok": True, "stopped": stopped, "cancelled": cancelled}


@shared_task(name="dashboard.health_heartbeat")
def health_heartbeat_task() -> dict:
    """Push health snapshot to all users with active dashboard connections."""
    from apps.accounts.models import User
    from apps.dashboard.health import get_celery_status, get_market_feed_status
    from apps.dashboard.publish import publish_dashboard
    from apps.dashboard.views import build_health_payload

    payload = build_health_payload(user=None)
    payload["source"] = "health"
    for user_id in User.objects.filter(is_active=True).values_list("pk", flat=True):
        user_payload = {**payload}
        publish_dashboard(user_id, user_payload)
    return {"ok": True, "hl_market_feed": get_market_feed_status(), "celery": get_celery_status()}
