"""Execution app signals — publish logs to dashboard WebSocket."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ExecutionLog


def _log_message(log: ExecutionLog) -> str:
    event = log.event
    payload = log.payload or {}
    if event == "bar.received":
        return f"Received {payload.get('timeframe', '?')} candle for {payload.get('symbol', '?')}"
    if event == "strategy.evaluated":
        return f"Strategy '{payload.get('name', '?')}' evaluated: {payload.get('action', 'No Action')}"
    if event == "order.placed":
        return (
            f"Signal Triggered: {payload.get('side', '').upper()} "
            f"{payload.get('symbol', '?')} at {payload.get('price', '?')}. Pushing to Celery..."
        )
    if event == "order.filled":
        return f"Exchange Response: Order #{payload.get('exchange_order_id', '?')} Filled."
    if event == "order.blocked":
        return f"Order blocked: {payload.get('reason', 'unknown')}"
    if event == "kill_switch.triggered":
        return "Kill switch triggered — all strategies stopped."
    return event


@receiver(post_save, sender=ExecutionLog)
def publish_execution_log(sender, instance: ExecutionLog, created, **kwargs):
    if not created:
        return

    user_id = None
    if instance.strategy_id:
        from apps.strategies.models import Strategy

        user_id = (
            Strategy.objects.filter(pk=instance.strategy_id)
            .values_list("user_id", flat=True)
            .first()
        )
    else:
        user_id = (instance.payload or {}).get("user_id")

    if not user_id:
        return

    from apps.dashboard.publish import publish_dashboard

    publish_dashboard(
        user_id,
        {
            "source": "log",
            "level": instance.level,
            "event": instance.event,
            "message": _log_message(instance),
            "payload": instance.payload,
            "created_at": instance.created_at.isoformat(),
            "strategy_id": instance.strategy_id,
        },
    )
