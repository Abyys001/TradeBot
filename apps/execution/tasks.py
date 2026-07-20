"""Execution lifecycle maintenance tasks (Tabdeal futures).

Reconciliation answers one question for every order left in a non-terminal state:
*what actually happened to it on the exchange?* Tabdeal market orders normally fill
synchronously, so a lingering non-terminal record means we lost the response (network
timeout, worker crash, WS gap). We resolve it against the exchange's own record via
``get_order`` (when we have an exchange order id) or ``all_orders`` (§3.4 — "did the
order land at all?", matched by client order id).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.utils import timezone

from apps.execution.models import ExecutionLog, OrderRecord

logger = logging.getLogger(__name__)

_TERMINAL = {"filled", "rejected", "canceled", "expired"}
_NON_TERMINAL = ["pending", "submitted", "partially_filled"]

# Tabdeal/FAPI order status → OrderRecord.status (mirrors TabdealLiveBroker._status_map).
_STATUS_MAP = {
    "NEW": "submitted",
    "PARTIALLY_FILLED": "partially_filled",
    "FILLED": "filled",
    "CANCELED": "canceled",
    "CANCELLED": "canceled",
    "REJECTED": "rejected",
    "EXPIRED": "expired",
}


def _is_tabdeal(cred) -> bool:
    from apps.credentials.models import Exchange

    return cred is not None and getattr(cred, "is_active", False) and cred.exchange == Exchange.TABDEAL


def _client(cred):
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    return TabdealFuturesClient(cred)


def _map_status(raw_status: str) -> str | None:
    return _STATUS_MAP.get((raw_status or "").upper())


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _resolve_order(client, rec: OrderRecord) -> dict | None:
    """The exchange's record for ``rec``: by order id if known, else by client id."""
    if rec.exchange_order_id:
        try:
            return client.get_order(rec.symbol, int(rec.exchange_order_id))
        except Exception:  # noqa: BLE001 — fall through to client-id scan
            pass
    if rec.client_order_id:
        try:
            orders = client.all_orders(rec.symbol, limit=100)
        except Exception:  # noqa: BLE001
            return None
        for o in orders:
            if o.get("clientOrderId") == rec.client_order_id or o.get("origClientOrderId") == rec.client_order_id:
                return o
    return None


def _apply(rec: OrderRecord, order: dict) -> str | None:
    """Update ``rec`` from an exchange order dict. Returns the new status, or None."""
    new_status = _map_status(order.get("status", ""))
    fields = ["raw", "updated_at"]
    rec.raw = {**(rec.raw or {}), "reconcile": order}
    if new_status and new_status != rec.status:
        rec.status = new_status
        fields.append("status")
    executed = _dec(order.get("executedQty"))
    if executed is not None:
        rec.filled_size = executed
        fields.append("filled_size")
    avg = _dec(order.get("avgPrice") or order.get("avg_price"))
    if avg is not None and avg > 0:
        rec.avg_fill_price = avg
        fields.append("avg_fill_price")
    rec.save(update_fields=list(dict.fromkeys(fields)))
    return new_status


def reconcile_after_reconnect(credential_id: int) -> dict:
    """Resolve every non-terminal order for one credential after a WS reconnect (§3.4)."""
    from apps.credentials.models import ExchangeCredential

    cred = ExchangeCredential.objects.filter(pk=credential_id).first()
    if not _is_tabdeal(cred):
        return {"ok": True, "reconciled": 0}

    client = _client(cred)
    qs = OrderRecord.objects.select_related("strategy").filter(
        strategy__credential_id=credential_id, status__in=_NON_TERMINAL,
    )[:200]

    reconciled = 0
    for rec in qs:
        order = _resolve_order(client, rec)
        if order is None:
            continue
        new_status = _apply(rec, order)
        reconciled += 1
        if new_status:
            ExecutionLog.objects.create(
                strategy=rec.strategy, level="info",
                event=f"order.reconciled.{new_status}",
                payload={"order_id": rec.pk, "client_order_id": rec.client_order_id},
            )
    logger.info("reconcile_after_reconnect cred=%s: %d orders", credential_id, reconciled)
    return {"ok": True, "reconciled": reconciled}


@shared_task(name="execution.reconcile_orders")
def reconcile_orders_task() -> dict:
    """Best-effort reconciliation for non-terminal orders across all Tabdeal accounts."""
    cutoff = timezone.now() - timedelta(hours=24)
    qs = OrderRecord.objects.select_related("strategy", "strategy__credential").filter(
        status__in=_NON_TERMINAL, created_at__gte=cutoff,
    )[:200]

    reconciled = 0
    for rec in qs:
        cred = getattr(rec.strategy, "credential", None)
        if not _is_tabdeal(cred):
            continue
        try:
            order = _resolve_order(_client(cred), rec)
            if order is None:
                continue
            _apply(rec, order)
            reconciled += 1
        except Exception as exc:  # noqa: BLE001
            logger.info("reconcile failed: %s", type(exc).__name__)
            ExecutionLog.objects.create(
                strategy=rec.strategy, level="warning", event="order.reconcile_failed",
                payload={"order_id": rec.pk, "error": type(exc).__name__},
            )
    return {"ok": True, "reconciled": reconciled}


@shared_task(name="execution.retry_stale_orders")
def retry_stale_orders_task() -> dict:
    """Sweep orders stuck ``submitted``/``partially_filled`` > 60s without an update.

    For each: if it is still in the live open-orders book → leave it submitted; else
    resolve its terminal state from the exchange record; if the exchange has no memory
    of it at all, mark it canceled. Returns {checked, restored, canceled, errors}.
    """
    cutoff = timezone.now() - timedelta(hours=24)
    stale_before = timezone.now() - timedelta(seconds=60)
    qs = OrderRecord.objects.select_related("strategy", "strategy__credential").filter(
        created_at__gte=cutoff, created_at__lte=stale_before,
        status__in=["submitted", "partially_filled"],
    )[:200]

    counts = {"checked": 0, "restored": 0, "canceled": 0, "errors": 0}
    open_cache: dict[tuple[int, str], set[str]] = {}

    for rec in qs:
        cred = getattr(rec.strategy, "credential", None)
        if not _is_tabdeal(cred):
            continue
        counts["checked"] += 1
        try:
            client = _client(cred)
            key = (cred.pk, rec.symbol)
            if key not in open_cache:
                open_cache[key] = {
                    str(o.get("orderId", "")) for o in client.open_orders(rec.symbol)
                }
            in_book = rec.exchange_order_id and str(rec.exchange_order_id) in open_cache[key]
        except Exception:  # noqa: BLE001
            logger.exception("retry_stale_orders: open-orders check failed rec=%s", rec.pk)
            counts["errors"] += 1
            continue

        if in_book:
            continue  # genuinely resting; leave as-is

        try:
            order = _resolve_order(client, rec)
        except Exception:  # noqa: BLE001
            counts["errors"] += 1
            continue

        if order is not None and _map_status(order.get("status", "")):
            _apply(rec, order)
            counts["restored"] += 1
            ExecutionLog.objects.create(
                strategy=rec.strategy, level="info", event="order.retry_resolved",
                payload={"order_id": rec.pk, "status": rec.status},
            )
        else:
            rec.status = "canceled"
            rec.raw = {**(rec.raw or {}), "retry_expired": True}
            rec.save(update_fields=["status", "raw", "updated_at"])
            ExecutionLog.objects.create(
                strategy=rec.strategy, level="info", event="order.retry_expired",
                payload={"order_id": rec.pk, "client_order_id": rec.client_order_id},
            )
            counts["canceled"] += 1

    logger.info("retry_stale_orders: %s", counts)
    return {"ok": True, **counts}
