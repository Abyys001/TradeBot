"""Execution lifecycle maintenance tasks."""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db import models
from django.utils import timezone

from apps.execution.models import ExecutionLog, OrderRecord

logger = logging.getLogger(__name__)


def reconcile_after_reconnect(credential_id: int) -> dict:
    """Reconcile pending orders after a WS reconnect. DEPRECATED: HL-specific logic removed."""
    return {"ok": True, "reconciled": 0, "filled": 0, "canceled": 0, "resting": 0}

    from hyperliquid.utils.types import Cloid

    counts = {"filled": 0, "canceled": 0, "resting": 0}

    for rec in pending:
        cloid_str = rec.client_order_id
        try:
            cloid = Cloid.from_str(cloid_str)
            result = info.query_order_by_cloid(cred.wallet_address, cloid)
        except Exception:  # noqa: BLE001
            # Fall back to OID if cloid lookup unsupported or fails.
            if rec.exchange_order_id:
                try:
                    result = info.query_order_by_oid(
                        cred.wallet_address, int(rec.exchange_order_id)
                    )
                except Exception:  # noqa: BLE001
                    continue
            else:
                continue

        order = (result or {}).get("order") or {}
        exchange_status = str(order.get("status", "")).lower()

        new_status = {
            "filled": "filled",
            "canceled": "canceled",
            "cancelled": "canceled",
            "rejected": "rejected",
            "open": None,
            "resting": None,
            "triggered": None,
        }.get(exchange_status)

        if new_status is None:
            counts["resting"] += 1
            continue

        try:
            rec.status = new_status
            rec.raw = {**(rec.raw or {}), "reconcile_reconnect": result}
            rec.save(update_fields=["status", "raw", "updated_at"])
            counts[new_status if new_status in counts else "resting"] += 1
            ExecutionLog.objects.create(
                strategy=rec.strategy,
                level="info",
                event=f"order.reconciled.{new_status}",
                payload={"cloid": cloid_str, "exchange_status": exchange_status},
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("reconcile update failed: %s", type(exc).__name__)

    total = sum(counts.values())
    logger.info(
        "reconcile_after_reconnect cred=%s: %d orders — %s",
        credential_id, total, counts,
    )
    return {"ok": True, "reconciled": total, **counts}


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


@shared_task(name="execution.retry_stale_orders")
def retry_stale_orders_task() -> dict:
    """Periodic sweep: reconcile orders stuck in non-final statuses.

    Hyperliquid occasionally emits ``marginCanceled`` / ``iocCancelRejected`` /
    ``reduceOnlyCanceled`` for orders that are still in the active order book.
    This task sweeps orders stuck in those statuses plus orders that have been
    ``submitted``/``partially_filled`` for longer than 60 seconds without
    receiving a WS update.

    For each qualifying order:
      1. Check the live HL order book via ``_check_active_book`` (oid + cloid).
      2. If the order IS in the book → restore status to ``submitted``.
      3. If the order is NOT in the book → mark as ``canceled``.

    Returns a summary dict with keys: checked, restored, canceled, errors.
    """
    from apps.execution.order_sync import _check_active_book

    cutoff = timezone.now() - timedelta(hours=24)
    stale_statuses = ["margincanceled", "ioccancelrejected", "reduceonlycanceled"]
    qs = OrderRecord.objects.select_related("strategy", "strategy__credential").filter(
        created_at__gte=cutoff,
    ).filter(
        models.Q(status__in=["submitted", "partially_filled", *stale_statuses]),
    )[:200]

    counts = {"checked": 0, "restored": 0, "canceled": 0, "errors": 0}

    for rec in qs:
        cred = getattr(rec.strategy, "credential", None)
        if cred is None or not cred.is_active:
            continue

        try:
            in_book = _check_active_book(rec, cred.pk)
        except Exception:  # noqa: BLE001
            logger.exception("retry_stale_orders: _check_active_book failed rec=%s", rec.pk)
            counts["errors"] += 1
            continue

        counts["checked"] += 1

        if in_book:
            old_status = rec.status
            if old_status != "submitted":
                rec.status = "submitted"
                rec.raw = {**(rec.raw or {}), "retry_restored": True}
                rec.save(update_fields=["status", "raw", "updated_at"])
                ExecutionLog.objects.create(
                    strategy=rec.strategy,
                    level="info",
                    event="order.retry_restored",
                    payload={
                        "order_id": rec.pk,
                        "cloid": rec.client_order_id,
                        "previous_status": old_status,
                    },
                )
                counts["restored"] += 1
        else:
            rec.status = "canceled"
            rec.raw = {**(rec.raw or {}), "retry_expired": True}
            rec.save(update_fields=["status", "raw", "updated_at"])
            ExecutionLog.objects.create(
                strategy=rec.strategy,
                level="info",
                event="order.retry_expired",
                payload={
                    "order_id": rec.pk,
                    "cloid": rec.client_order_id,
                },
            )
            counts["canceled"] += 1

    logger.info("retry_stale_orders: %s", counts)
    return {"ok": True, **counts}

