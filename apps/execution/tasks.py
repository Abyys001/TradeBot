"""Execution lifecycle maintenance tasks."""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.execution.models import ExecutionLog, OrderRecord
from apps.exchange.hl_client import build_info

logger = logging.getLogger(__name__)


@shared_task(name="execution.reconcile_orders")
def reconcile_orders_task() -> dict:
    """Best-effort reconciliation for non-final orders (covers WS disconnect)."""
    cutoff = timezone.now() - timedelta(hours=24)
    qs = OrderRecord.objects.select_related("strategy", "strategy__credential").filter(
        status__in=["pending", "submitted", "partially_filled"],
        created_at__gte=cutoff,
    )[:200]

    reconciled = 0
    for rec in qs:
        cred = getattr(rec.strategy, "credential", None)
        if cred is None or not cred.is_active:
            continue
        try:
            info = build_info(cred.network)
            if rec.exchange_order_id:
                st = info.query_order_by_oid(cred.wallet_address, int(rec.exchange_order_id))
            else:
                continue
            rec.raw = {**(rec.raw or {}), "reconcile": st}
            rec.save(update_fields=["raw", "updated_at"])
            reconciled += 1
        except Exception as exc:  # noqa: BLE001
            logger.info("reconcile failed: %s", type(exc).__name__)
            ExecutionLog.objects.create(
                strategy=rec.strategy,
                level="warning",
                event="order.reconcile_failed",
                payload={"order_id": rec.pk, "error": type(exc).__name__},
            )

    return {"ok": True, "reconciled": reconciled}

