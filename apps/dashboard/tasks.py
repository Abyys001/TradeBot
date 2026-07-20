"""Dashboard Celery tasks: emergency stop and health heartbeat."""
from __future__ import annotations

import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

KILL_SWITCH_LOCK_TTL = 60  # seconds


@shared_task(name="dashboard.emergency_stop_all")
def emergency_stop_all_task(user_id: int) -> dict:
    """Stop all active strategies and optionally close exchange positions.

    Uses a Redis lock to prevent duplicate kill-switch invocations.
    """
    from apps.accounts.models import User
    from apps.credentials.models import ExchangeCredential
    from apps.execution.models import ExecutionLog
    from apps.strategies.models import Strategy
    from apps.transpiler.tasks import stop_live_strategy_task

    # Prevent duplicate kill-switch invocations.
    lock_key = f"kill_switch_lock:{user_id}"
    if not cache.add(lock_key, "1", KILL_SWITCH_LOCK_TTL):
        return {"ok": False, "reason": "kill_switch_already_in_progress"}

    user = User.objects.get(pk=user_id)
    user.is_trading_enabled = False
    user.save(update_fields=["is_trading_enabled"])

    stopped = []
    for strategy in Strategy.objects.filter(user=user, status=Strategy.Status.ACTIVE):
        stop_live_strategy_task.delay(strategy.pk)
        strategy.status = Strategy.Status.STOPPED
        strategy.save(update_fields=["status"])
        stopped.append(strategy.pk)

    # HL-specific cancel/close removed
    cancelled = []

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
