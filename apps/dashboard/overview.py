"""Aggregate dashboard overview stats for the authenticated user."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.credentials.models import ExchangeCredential
from apps.execution.models import ExecutionLog, OrderRecord
from apps.execution.serializers import ExecutionLogSerializer, OrderRecordSerializer
from apps.strategies.models import Strategy, StrategyState


def build_overview_payload(user) -> dict:
    strategies_qs = Strategy.objects.filter(user=user)
    status_counts = {row["status"]: row["count"] for row in strategies_qs.values("status").annotate(count=Count("id"))}
    total_strategies = sum(status_counts.values())

    orders_qs = OrderRecord.objects.filter(strategy__user=user)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    filled_statuses = {"filled", "submitted", "partially_filled"}

    orders_total = orders_qs.count()
    orders_today = orders_qs.filter(created_at__gte=today_start).count()
    orders_filled = orders_qs.filter(status__in=filled_statuses).count()

    pnl_agg = StrategyState.objects.filter(strategy__user=user).aggregate(total=Sum("pnl"))
    total_pnl = pnl_agg["total"] or Decimal("0")
    strategies_with_pnl = StrategyState.objects.filter(strategy__user=user).exclude(pnl=0).count()

    since_24h = timezone.now() - timedelta(hours=24)
    logs_qs = ExecutionLog.objects.filter(
        Q(strategy__user=user) | Q(strategy__isnull=True, payload__user_id=user.pk)
    )
    errors_24h = logs_qs.filter(level=ExecutionLog.Level.ERROR, created_at__gte=since_24h).count()
    warnings_24h = logs_qs.filter(level=ExecutionLog.Level.WARNING, created_at__gte=since_24h).count()

    creds_qs = ExchangeCredential.objects.filter(user=user)
    creds_total = creds_qs.count()
    creds_active = creds_qs.filter(is_active=True).count()

    recent_orders = OrderRecordSerializer(
        orders_qs.select_related("strategy").order_by("-created_at")[:5],
        many=True,
    ).data
    recent_logs = ExecutionLogSerializer(
        logs_qs.order_by("-created_at")[:5],
        many=True,
    ).data

    return {
        "strategies": {
            "total": total_strategies,
            "active": status_counts.get(Strategy.Status.ACTIVE, 0),
            "draft": status_counts.get(Strategy.Status.DRAFT, 0),
            "paused": status_counts.get(Strategy.Status.PAUSED, 0),
            "stopped": status_counts.get(Strategy.Status.STOPPED, 0),
        },
        "orders": {
            "total": orders_total,
            "today": orders_today,
            "filled": orders_filled,
        },
        "pnl": {
            "total_unrealized": str(total_pnl),
            "strategies_with_pnl": strategies_with_pnl,
        },
        "logs": {
            "errors_24h": errors_24h,
            "warnings_24h": warnings_24h,
        },
        "credentials": {
            "total": creds_total,
            "active": creds_active,
        },
        "recent_orders": recent_orders,
        "recent_logs": recent_logs,
    }
